"""Shared asynchronous chunked sender for the BBS text stream.

`PostTyper` (article body / title) and `PasteSender` (clipboard paste) both write sanitised
cp950 bytes to the same connection in small chunks, paced by a server-quiet window and bounded
by a hard timeout.  This base owns that machinery so neither subclass repeats the timer, lock,
connection-guard, cancellation or abort-message boilerplate.

Safety invariants kept here: the caller can only send pre-built bytes, every chunk is gated by a
subclass guard, and a dropped link, a stall or a cancel aborts for good -- there is no resume and
no retry.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from ..logging_setup import get_logger
from .client import State

log = get_logger("chunked")

CHUNK_BYTES = 100
IDLE_MS = 120
MAX_WAIT_MS = 3000


class ChunkedSender(QObject):
    """Paced byte-stream sender shared by the typer and the paster.

    Subclasses set `owner` / `action` / `log_name`, build their chunks, call `_begin()`, then
    `_next()` exactly once to start.  They customise behaviour through the `_*_message` hooks,
    `_guard()` (per-chunk precondition) and `_count_chunk()`.
    """

    progress = Signal(int, int)      # chunks done, total
    finished = Signal(bool, str)     # ok, message (also emitted on abort with ok=False)

    owner: str = ""
    action: str = ""
    log_name: str = "send"

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.s = session
        self.running = False
        self._chunks: list[bytes] = []
        self._i = 0
        self._quiet = QTimer(self)
        self._quiet.setSingleShot(True)
        self._quiet.setInterval(IDLE_MS)
        self._quiet.timeout.connect(self._next)
        self._cap = QTimer(self)
        self._cap.setSingleShot(True)
        self._cap.setInterval(MAX_WAIT_MS)
        self._cap.timeout.connect(lambda: self._abort(self._timeout_message()))
        self.s.client.dataReceived.connect(self._on_data)
        self.s.client.stateChanged.connect(self._on_state)

    # ----------------------------------------------------------------- hooks
    def _guard(self) -> str | None:
        """Return the abort reason when the next chunk must not be sent, else None."""
        return None

    def _timeout_message(self) -> str:
        return "伺服器持續回傳資料或無回應，已停止。"

    def _disconnect_message(self) -> str:
        return "連線中斷；不會自動重連或重送。請目視確認終端機現況。"

    def _cancel_message(self) -> str:
        return "使用者取消；已送出的部分不會自動清除或重送。"

    def _count_chunk(self, chunk: bytes) -> None:
        pass

    def _abort_detail(self) -> str:
        return f"共 {len(self._chunks)} 段中的 {self._i} 段"

    def _success_message(self) -> str:
        return "傳送完成。"

    # ------------------------------------------------------------- lifecycle
    def _acquire(self) -> str | None:
        lock = getattr(self.s, "send_lock", None)
        if lock is not None and not lock.acquire(self.owner):
            return f"{lock.label()}進行中，已暫停{self.action}；請等它結束後再試。"
        return None

    def _begin(self, chunks: list[bytes], quiet_ms: int) -> None:
        self._chunks = chunks
        self._i = 0
        self.running = True
        self._quiet.setInterval(quiet_ms)

    def _next(self) -> None:
        if not self.running:
            return
        self._cap.stop()
        if self.s.client.state is not State.CONNECTED:
            self._abort(self._disconnect_message())
            return
        why = self._guard()
        if why is not None:
            self._abort(why)
            return
        if self._i >= len(self._chunks):
            self.running = False
            self._release()
            self.finished.emit(True, self._success_message())
            return
        chunk = self._chunks[self._i]
        if not self.s.client.send(chunk):
            self._abort("傳送失敗。")
            return
        self._count_chunk(chunk)
        self._i += 1
        self.progress.emit(self._i, len(self._chunks))
        self._cap.start()
        self._quiet.start()                  # next chunk after the server has been quiet

    def _on_data(self, _data: bytes) -> None:
        if self.running:
            self._quiet.start()              # still receiving: restart the quiet window

    def _on_state(self, st: State) -> None:
        if self.running and st is not State.CONNECTED:
            self._abort(self._disconnect_message())

    def _release(self) -> None:
        lock = getattr(self.s, "send_lock", None)
        if lock is not None:
            lock.release(self.owner)

    def _abort(self, why: str) -> None:
        if not self.running:
            return
        self.running = False
        self._quiet.stop()
        self._cap.stop()
        self._release()
        log.warning("%s aborted after %d/%d chunks: %s", self.log_name, self._i, len(self._chunks), why)
        self.finished.emit(False, f"{why}（{self._abort_detail()}）"
                                  "請先目視確認終端機內容；程式不會自動重試或重送。")

    def cancel(self, why: str | None = None) -> None:
        if self.running:
            self._abort(why or self._cancel_message())
