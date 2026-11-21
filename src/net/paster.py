"""Paste text into the BBS in small chunks, using the same rhythm as the article typer.

Only sanitised cp950 text is sent (characters Big5 cannot encode become '?'). Every chunk is re-checked against the
caller's guard (automatic typing / assisted login) and the connection state; a drop or a
lock stops the run for good with no retry.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Callable

from ..compose import INVISIBLE
from ..logging_setup import get_logger
from .chunked import CHUNK_BYTES, IDLE_MS, ChunkedSender
from .client import State
from .poster import build_chunks
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
        elif unicodedata.category(ch) == "Cc" or INVISIBLE.match(ch):   # zero-width / emoji glue would become '?'
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


class PasteSender(ChunkedSender):
    owner = PASTE
    action = "貼上"
    log_name = "paste"

    def __init__(self, session: PttSession, blocked: Callable[[], str | None], parent=None):
        super().__init__(session, parent)
        self._blocked = blocked
        self.chars_sent = 0
        self.total_chars = 0

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
        chunks = build_chunks(text, CHUNK_BYTES)           # unencodable chars become '?'; no lock is taken on failure
        why = self._acquire()
        if why:
            return why
        self.chars_sent = 0
        self.total_chars = len(text.replace("\n", ""))
        self._begin(chunks, IDLE_MS)
        log.info("paste started: %d chars, %d chunks", self.total_chars, len(self._chunks))
        self._next()
        return None

    def _guard(self) -> str | None:
        why = self._blocked()
        return None if not why else why + "已停止貼上；不會重送。"

    def _timeout_message(self) -> str:
        return "伺服器持續回傳資料或無回應，已停止貼上。"

    def _disconnect_message(self) -> str:
        return "連線已中斷，已停止貼上；不會重送。"

    def _cancel_message(self) -> str:
        return "使用者取消貼上。"

    def _count_chunk(self, chunk: bytes) -> None:
        self.chars_sent += len(chunk.decode("cp950", "replace").replace("\r", ""))

    def _abort_detail(self) -> str:
        return f"已送出 {self.chars_sent}／{self.total_chars} 字，共 {len(self._chunks)} 段中的 {self._i} 段"

    def _success_message(self) -> str:
        return (f"貼上完成：已送出 {self.chars_sent} 字（{len(self._chunks)} 段）。"
                "程式只送出文字，未按 Enter／存檔；請在終端機確認內容。")
