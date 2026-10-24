"""Type a title / article body into the logged-in PTT terminal -- and STOP before any final submit.

Hard guarantees (covered by tests/test_poster.py against a fake BBS that records every byte):
* Only printable text (cp950-encodable) and CR line breaks are ever sent. Never Ctrl-X / Ctrl-Q /
  ESC / save / confirm keys. No trailing Enter after the title, no Ctrl-X after the body.
* Preflight must positively recognise the screen (title prompt / empty editor). Anything else: 0 bytes.
* The screen is re-checked before every chunk; a mismatch, a dropped connection, a stall or a
  user cancel aborts for good. There is no resume and no retry: re-typing needs a new, explicit start.
"""
from __future__ import annotations

import enum

from PySide6.QtCore import QObject, QTimer, Signal

from ..logging_setup import get_logger
from ..terminal.detect import Kind, editor_is_empty, reply_editor_ready, title_prompt_is_empty
from .client import State
from .sendlock import PASTE, TYPING
from .session import PttSession

log = get_logger("poster")
CHUNK_BYTES = 100
IDLE_MS = 120
MAX_WAIT_MS = 3000
MONEY_CHUNK_BYTES = 2          # one cp950 character (or one ASCII byte)
MONEY_CHAR_MS = 500            # PTT: at most 1 P per 2 seconds = 4 chars per 2 s


class Target(enum.Enum):
    TITLE = "title"
    BODY = "body"
    REPLY_BODY = "reply_body"


def encode_big5(text: str) -> tuple[bytes | None, list[tuple[int, str]]]:
    """Strict cp950 encode. Returns (bytes, []) or (None, [(index, char), ...unencodable])."""
    try:
        return text.encode("cp950"), []                  # the normal case: one C-level call
    except UnicodeEncodeError:
        pass
    bad = []
    for i, ch in enumerate(text):
        try:
            ch.encode("cp950")
        except UnicodeEncodeError:
            bad.append((i, ch))
    if bad:
        return None, bad
    return text.encode("cp950"), []


def build_chunks(text: str, limit: int = CHUNK_BYTES) -> list[bytes]:
    """Split into <=limit byte chunks at character boundaries; line breaks become CR."""
    chunks: list[bytes] = []
    lines = text.split("\n")
    for li, line in enumerate(lines):
        cur = b""
        for ch in line:
            b = ch.encode("cp950")
            if len(cur) + len(b) > limit:
                chunks.append(cur)
                cur = b""
            cur += b
        if li < len(lines) - 1:
            if cur and len(cur) + 1 > limit:
                chunks.append(cur)
                cur = b""
            cur += b"\r"                      # line break between lines; none after the last line
        if cur:
            chunks.append(cur)
    return chunks


def preflight(session: PttSession, target: Target, text: str, allow_nonempty: bool = False,
              pasting: bool = False) -> str | None:
    """Return None when typing is allowed, else the (user-facing) reason it is not."""
    lock = getattr(session, "send_lock", None)
    if pasting or (lock is not None and lock.owned_by(PASTE)):
        return "貼上進行中，已暫停自動輸入；請等貼上結束後再試。"
    if lock is not None and lock.owner() == TYPING:
        return "已有自動輸入進行中。"
    if session.client.state is not State.CONNECTED:
        return "尚未連線。"
    if not session.logged_in:
        return "尚未確認登入（畫面未曾進入主功能表）。請先登入，或在終端機中操作到主功能表。"
    if not text.strip():
        return "內容是空的。"
    for ch in text:
        if (ord(ch) < 0x20 and ch != "\n") or ord(ch) in (0x7F, 0x1B) or 0x80 <= ord(ch) <= 0x9F:
            return f"內容含有控制字元 U+{ord(ch):04X}，可能觸發 PTT 快捷鍵，已拒絕輸入。"
    if target is Target.TITLE and "\n" in text:
        return "標題不可含換行。"
    data, bad = encode_big5(text)
    if data is None:
        shown = "、".join(f"「{c}」(第 {i + 1} 字)" for i, c in bad[:5])
        return f"含有無法以 Big5 編碼的字元 {shown}，PTT 會顯示成亂碼，已拒絕輸入。請改寫後再試。"
    k = session.kind
    if target is Target.TITLE:
        if k is not Kind.TITLE_PROMPT:
            return f"目前畫面不是『標題』輸入提示（偵測為：{k.value}）。請先在終端機中進到發文的標題提示。"
        if not title_prompt_is_empty(session.screen) and not allow_nonempty:
            return "標題欄已有內容，已拒絕輸入（避免覆蓋）。"
    elif target is Target.REPLY_BODY:
        if k is not Kind.EDITOR:
            return f"目前畫面不是文章編輯畫面（偵測為：{k.value}）。請先在 PTT 文章按 r，Enter 進入回覆編輯區。"
        if not editor_is_empty(session.screen) and not allow_nonempty and not reply_editor_ready(session.screen):
            return ("編輯區不是空白，且不像 PTT 的回覆引文（游標需在開頭，且畫面要有『※ 引述』或『: 』引文）。"
                    "請確認已在回覆編輯區，或勾選進階的允許非空白編輯區。")
    else:
        if k is not Kind.EDITOR:
            return f"目前畫面不是文章編輯畫面（偵測為：{k.value}）。請先在終端機中進到編輯畫面。"
        if not editor_is_empty(session.screen) and not allow_nonempty:
            return "編輯區不是空的，已拒絕輸入（避免插入到既有內容）。"
    return None


class PostTyper(QObject):
    started = Signal(object)         # Target -- emitted BEFORE the first byte is sent (write-ahead hook)
    progress = Signal(int, int)      # chunks done, total
    finished = Signal(bool, str)     # ok, message (also emitted on abort with ok=False)

    def __init__(self, session: PttSession, parent=None):
        super().__init__(parent)
        self.s = session
        self.running = False
        self.bytes_sent = 0
        self._chunks: list[bytes] = []
        self._i = 0
        self._target = Target.BODY
        self._quiet = QTimer(self)
        self._quiet.setSingleShot(True)
        self._quiet.setInterval(IDLE_MS)
        self._quiet.timeout.connect(self._next)
        self._cap = QTimer(self)
        self._cap.setSingleShot(True)
        self._cap.setInterval(MAX_WAIT_MS)
        self._cap.timeout.connect(lambda: self._abort("伺服器持續回傳資料或無回應，已停止輸入。"))
        self.s.client.dataReceived.connect(self._on_data)
        self.s.client.stateChanged.connect(self._on_state)

    def start(self, target: Target, text: str, allow_nonempty: bool = False,
              pasting: bool = False, money_pace: bool = False) -> str | None:
        """Begin typing. Returns None if started, else the reason it was refused (nothing sent).

        money_pace sends one character every ~0.5 s, the rate PTT's P-coin rule
        rewards (4 chars per 2 seconds); this can take minutes for long articles.
        """
        if self.running:
            return "已有輸入進行中。"
        why = preflight(self.s, target, text, allow_nonempty, pasting)
        if why:
            log.info("typing refused (%s): %s", target.value, why)
            return why
        lock = getattr(self.s, "send_lock", None)
        if lock is not None and not lock.acquire(TYPING):
            return f"{lock.label()}進行中，已暫停自動輸入；請等它結束後再試。"
        self._target, self._i, self.bytes_sent = target, 0, 0
        self._chunks = build_chunks(text, limit=MONEY_CHUNK_BYTES if money_pace else CHUNK_BYTES)
        self._quiet.setInterval(MONEY_CHAR_MS if money_pace else IDLE_MS)
        self.running = True
        self.started.emit(target)            # caller records "input started" durably first
        log.info("typing %s: %d chunks (%s)", target.value, len(self._chunks),
                 "money pace" if money_pace else "normal")
        self._next()
        return None

    def cancel(self) -> None:
        if self.running:
            self._abort("使用者取消輸入；已輸入的部分不會自動清除或重送。")

    # ----------------------------------------------------------------- internals
    def _screen_ok(self) -> bool:
        k = self.s.kind
        if self._target is Target.TITLE:
            return k is Kind.TITLE_PROMPT          # the typed echo stays on the '標題：' row, so every chunk can be verified
        return k is Kind.EDITOR

    def _next(self) -> None:
        if not self.running:
            return
        self._cap.stop()
        if self.s.client.state is not State.CONNECTED:
            self._abort("連線中斷。")
            return
        if self._i >= len(self._chunks):
            self.running = False
            self._release()
            self.finished.emit(True, "傳送完成：程式只確認資料已送出，並不代表伺服器已完整收到。請在終端機逐行核對內容；程式不會代按存檔或送出，請自行確認／送出。")
            return
        if not self._screen_ok():
            self._abort(f"輸入途中畫面不是預期的畫面（偵測為：{self.s.kind.value}），已停止；請目視確認終端機內容。")
            return
        chunk = self._chunks[self._i]
        if not self.s.client.send(chunk):
            self._abort("傳送失敗。")
            return
        self.bytes_sent += len(chunk)
        self._i += 1
        self.progress.emit(self._i, len(self._chunks))
        self._cap.start()
        self._quiet.start()                  # next chunk after the server has been quiet for IDLE_MS

    def _on_data(self, _data: bytes) -> None:
        if self.running:
            self._quiet.start()              # still receiving: restart the quiet window

    def _on_state(self, st: State) -> None:
        if self.running and st is not State.CONNECTED:
            self._abort("連線中斷；不會自動重連或重送。請重新連線並目視檢查編輯區現況。")

    def _release(self) -> None:
        lock = getattr(self.s, "send_lock", None)
        if lock is not None:
            lock.release(TYPING)

    def _abort(self, why: str) -> None:
        if not self.running:
            return
        self.running = False
        self._quiet.stop()
        self._cap.stop()
        self._release()
        log.warning("typing aborted after %d/%d chunks: %s", self._i, len(self._chunks), why)
        self.finished.emit(False, f"{why}（已送出 {self.bytes_sent} bytes，共 {len(self._chunks)} 段中的 {self._i} 段）")
