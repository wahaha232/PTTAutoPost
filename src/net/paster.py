"""Paste text into the BBS in small chunks, using the same rhythm as the article typer.

Only sanitised, cp950-encodable text is sent. Every chunk is re-checked against the
caller's guard (automatic typing / assisted login) and the connection state; a drop or a
lock stops the run for good with no retry.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from ..logging_setup import get_logger
from .client import State
from .poster import CHUNK_BYTES, IDLE_MS, MAX_WAIT_MS, build_chunks
from .sendlock import PASTE
from .session import PttSession

log = get_logger("paster")
MAX_PASTE_CHARS = 5000
PREVIEW_CHARS = 200


def sanitize_paste(text: str) -> tuple[str, int]:
    """Normalise line breaks, expand tabs, remove ESC/control characters. Returns (text, removed)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    removed = 0
    for ch in text:
        if ch == "\n":
            out.append("\n")
        elif ch == "\t":
            out.append("    ")
        elif unicodedata.category(ch) == "Cc":
            removed += 1
        else:
            out.append(ch)
    return "".join(out), removed


def paste_stats(text: str) -> tuple[int, int]:
    """(characters excluding line breaks, lines)."""
    return len(text.replace("\n", "")), text.count("\n") + 1


def paste_preview(text: str, max_lines: int = 5, width: int = 100) -> str:
    lines = text.split("\n")
    head = [line if len(line) <= width else line[:width] + "…" for line in lines[:max_lines]]
    out = "\n".join(head)
    if len(lines) > max_lines:
        out += f"\n…（其餘 {len(lines) - max_lines} 行）"
    return out


class PasteSender(QObject):
    progress = Signal(int, int)
    finished = Signal(bool, str)

    def __init__(self, session: PttSession, blocked: Callable[[], str | None], parent=None):
        super().__init__(parent)
        self.s = session
        self._blocked = blocked
        self.running = False
        self.chars_sent = 0
        self.total_chars = 0
        self._chunks: list[bytes] = []
        self._i = 0
        self._quiet = QTimer(self)
        self._quiet.setSingleShot(True)
        self._quiet.setInterval(IDLE_MS)
        self._quiet.timeout.connect(self._next)
        self._cap = QTimer(self)
        self._cap.setSingleShot(True)
        self._cap.setInterval(MAX_WAIT_MS)
        self._cap.timeout.connect(lambda: self._abort("伺服器持續回傳資料或無回應，已停止貼上。"))
        self.s.client.dataReceived.connect(self._on_data)
        self.s.client.stateChanged.connect(self._on_state)

    def start(self, text: str) -> str | None:
        """Start sending. Returns None if started, else the reason nothing was sent."""
        if self.running:
            return "已有貼上進行中。"
        if self.s.client.state is not State.CONNECTED:
            return "尚未連線，無法貼上。"
        why = self._blocked()
        if why:
            return why
        if not text:
            return "沒有可貼上的文字。"
        lock = getattr(self.s, "send_lock", None)
        if lock is not None and not lock.acquire(PASTE):
            return f"{lock.label()}進行中，已暫停貼上；請等它結束後再試。"
        self._chunks = build_chunks(text, CHUNK_BYTES)
        self._i = 0
        self.chars_sent = 0
        self.total_chars = len(text.replace("\n", ""))
        self.running = True
        log.info("paste started: %d chars, %d chunks", self.total_chars, len(self._chunks))
        self._next()
        return None

    def cancel(self, why: str = "使用者取消貼上。") -> None:
        self._abort(why)

    def _chunk_chars(self, chunk: bytes) -> int:
        return len(chunk.decode("cp950", "replace").replace("\r", ""))

    def _next(self) -> None:
        if not self.running:
            return
        self._cap.stop()
        if self.s.client.state is not State.CONNECTED:
            self._abort("連線已中斷，已停止貼上；不會重送。")
            return
        why = self._blocked()
        if why:
            self._abort(why + "已停止貼上；不會重送。")
            return
        if self._i >= len(self._chunks):
            self.running = False
            self._release()
            self.finished.emit(True, f"貼上完成：已送出 {self.chars_sent} 字（{len(self._chunks)} 段）。"
                                     "程式只送出文字，未按 Enter／存檔；請在終端機確認內容。")
            return
        chunk = self._chunks[self._i]
        if not self.s.client.send(chunk):
            self._abort("傳送失敗。")
            return
        self.chars_sent += self._chunk_chars(chunk)
        self._i += 1
        self.progress.emit(self._i, len(self._chunks))
        self._cap.start()
        self._quiet.start()

    def _on_data(self, _data: bytes) -> None:
        if self.running:
            self._quiet.start()

    def _on_state(self, st: State) -> None:
        if self.running and st is not State.CONNECTED:
            self._abort("連線已中斷，已停止貼上；不會重送。")

    def _release(self) -> None:
        lock = getattr(self.s, "send_lock", None)
        if lock is not None:
            lock.release(PASTE)

    def _abort(self, why: str) -> None:
        if not self.running:
            return
        self.running = False
        self._quiet.stop()
        self._cap.stop()
        self._release()
        log.warning("paste aborted after %d/%d chunks: %s", self._i, len(self._chunks), why)
        self.finished.emit(False, f"{why}（已送出 {self.chars_sent}／{self.total_chars} 字，"
                                  f"共 {len(self._chunks)} 段中的 {self._i} 段）"
                                  "請先目視確認終端機內容；程式不會自動重試或重送。")
