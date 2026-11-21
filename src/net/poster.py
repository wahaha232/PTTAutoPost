"""Type a title / article body into the logged-in PTT terminal -- and STOP before any final submit.

Hard guarantees (covered by tests/test_poster.py against a fake BBS that records every byte):
* Only printable cp950 text and CR line breaks are ever sent (characters Big5 cannot encode are sent
  as '?', invisible emoji joiners/selectors are dropped). Never Ctrl-X / Ctrl-Q /
  ESC / save / confirm keys. No trailing Enter after the title, no Ctrl-X after the body.
* Preflight must positively recognise the screen (title prompt / empty editor). Anything else: 0 bytes.
* The screen is re-checked before every chunk; a mismatch, a dropped connection, a stall or a
  user cancel aborts for good. There is no resume and no retry: re-typing needs a new, explicit start.
"""
from __future__ import annotations

import enum

from PySide6.QtCore import Signal

from ..compose import INVISIBLE
from ..logging_setup import get_logger
from ..terminal.detect import Kind, editor_is_empty, reply_editor_ready, title_prompt_is_empty
from .chunked import CHUNK_BYTES, IDLE_MS, ChunkedSender
from .client import State
from .sendlock import PASTE, TYPING
from .session import PttSession

log = get_logger("poster")
MONEY_CHUNK_BYTES = 2          # one cp950 character (or one ASCII byte)
MONEY_CHAR_MS = 500            # PTT: at most 1 P per 2 seconds = 4 chars per 2 s
# zero-width (non-)joiners, variation selectors and skin-tone modifiers: invisible glue inside one
# emoji; dropped so a single emoji becomes one '?' instead of "???"
EMOJI_GLUE = INVISIBLE        # same rule as the preview (compose.INVISIBLE), so widths agree


class Target(enum.Enum):
    TITLE = "title"
    BODY = "body"
    REPLY_BODY = "reply_body"


def encode_big5(text: str) -> tuple[bytes, list[tuple[int, str]]]:
    """cp950 encode; unencodable characters become '?' and emoji glue (EMOJI_GLUE) is dropped.

    Returns (bytes, []), or (bytes with '?' replacements, [(index, char), ...]) so the caller can warn
    without refusing the whole paste/typing run.
    """
    text = EMOJI_GLUE.sub("", text)
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
    return text.encode("cp950", "replace"), bad


def build_chunks(text: str, limit: int = CHUNK_BYTES) -> list[bytes]:
    """Split into <=limit byte chunks at character boundaries; line breaks become CR; unencodable chars become '?'."""
    chunks: list[bytes] = []
    lines = EMOJI_GLUE.sub("", text).split("\n")
    for li, line in enumerate(lines):
        cur = b""
        for ch in line:
            b = ch.encode("cp950", "replace")
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
    # Unencodable characters are replaced with '?' by build_chunks; they must not lock posting.
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


class PostTyper(ChunkedSender):
    started = Signal(object)         # Target -- emitted BEFORE the first byte is sent (write-ahead hook)

    owner = TYPING
    action = "自動輸入"
    log_name = "typing"

    def __init__(self, session: PttSession, parent=None):
        super().__init__(session, parent)
        self.bytes_sent = 0
        self.total_chars = 0
        self.sent_chars = 0
        self._target = Target.BODY

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
        why = self._acquire()
        if why:
            return why
        self._target = target
        self.bytes_sent = 0
        self.total_chars = sum(1 for ch in text if not ch.isspace() and ch.isprintable())
        self.sent_chars = 0
        chunks = build_chunks(text, limit=MONEY_CHUNK_BYTES if money_pace else CHUNK_BYTES)
        self._begin(chunks, MONEY_CHAR_MS if money_pace else IDLE_MS)
        self.started.emit(target)            # caller records "input started" durably first
        log.info("typing %s: %d chunks (%s)", target.value, len(self._chunks),
                 "money pace" if money_pace else "normal")
        self._next()
        return None

    # ----------------------------------------------------------------- internals
    def _screen_ok(self) -> bool:
        k = self.s.kind
        if self._target is Target.TITLE:
            return k is Kind.TITLE_PROMPT          # the typed echo stays on the '標題：' row, so every chunk can be verified
        return k is Kind.EDITOR

    def _guard(self) -> str | None:
        if self._screen_ok():
            return None
        return f"輸入途中畫面不是預期的畫面（偵測為：{self.s.kind.value}），已停止；請目視確認終端機內容。"

    def _timeout_message(self) -> str:
        return "伺服器持續回傳資料或無回應，已停止輸入。"

    def _disconnect_message(self) -> str:
        return "連線中斷；不會自動重連或重送。請重新連線並目視檢查編輯區現況。"

    def _cancel_message(self) -> str:
        return "使用者取消輸入；已輸入的部分不會自動清除或重送。"

    def _count_chunk(self, chunk: bytes) -> None:
        self.bytes_sent += len(chunk)
        self.sent_chars += sum(1 for ch in chunk.decode("cp950", errors="ignore")
                               if not ch.isspace() and ch.isprintable())

    def _abort_detail(self) -> str:
        return f"已送出 {self.bytes_sent} bytes，共 {len(self._chunks)} 段中的 {self._i} 段"

    def _success_message(self) -> str:
        return ("傳送完成：程式只確認資料已送出，並不代表伺服器已完整收到。請在終端機逐行核對內容；"
                "程式不會代按存檔或送出，請自行確認／送出。")
