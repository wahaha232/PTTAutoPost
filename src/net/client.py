"""WebSocket transport to PTT (Qt's QWebSocket: non-blocking, runs on the Qt event loop).

Facts verified against the live endpoint on 2026-10-15 (tools/probe_wss.py):
* `wss://ws.ptt.cc/bbs` completes the handshake only when an `Origin: https://term.ptt.cc`
  header is sent (HTTP 403 without it). Sub-protocol is optional; "binary" is accepted.
* The very first message begins with the literal text "HTTP/1.1 200 OK\\r\\n\\r\\n" (proxy header)
  followed by the login screen (Big5 + ANSI). That prefix is stripped here.
* The server ends the login screen with "請輸入代號，或以 guest 參觀，或以 new 註冊:".
Connection loss is reported once and NEVER retried automatically.
"""
from __future__ import annotations

import enum

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWebSockets import QWebSocket, QWebSocketHandshakeOptions

from ..logging_setup import get_logger
from .telnet import IacFilter

log = get_logger("net")
DEFAULT_URL = "wss://ws.ptt.cc/bbs"
ORIGIN = "https://term.ptt.cc"
_PROXY_PREFIX = b"HTTP/1.1 200 OK\r\n\r\n"


class State(enum.Enum):
    DISCONNECTED = "未連線"
    CONNECTING = "連線中"
    CONNECTED = "已連線"


class PttClient(QObject):
    stateChanged = Signal(object)        # State
    dataReceived = Signal(bytes)         # terminal bytes (proxy prefix removed)
    failed = Signal(str)                 # human readable reason (connect failure / dropped)

    def __init__(self, parent=None, connect_timeout_ms: int = 10000):
        super().__init__(parent)
        self.state = State.DISCONNECTED
        self._ws: QWebSocket | None = None
        self._first = True
        self._intentional_close = False
        self._connect_timeout_ms = connect_timeout_ms
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_connect_timeout)
        self.bytes_sent = 0
        self.bytes_received = 0
        self._iac = IacFilter()

    # ----------------------------------------------------------------- control
    def connect_to(self, url: str = DEFAULT_URL) -> None:
        if self.state is not State.DISCONNECTED:
            return
        self._first, self._intentional_close = True, False
        self.bytes_sent = self.bytes_received = 0
        self._iac = IacFilter()
        ws = QWebSocket(ORIGIN)
        self._ws = ws
        ws.connected.connect(self._on_connected)
        ws.disconnected.connect(self._on_disconnected)
        ws.errorOccurred.connect(self._on_error)
        ws.binaryMessageReceived.connect(self._on_message)
        ws.textMessageReceived.connect(lambda s: self._on_message(s.encode("utf-8", "replace")))
        opts = QWebSocketHandshakeOptions()
        opts.setSubprotocols(["binary"])
        self._set_state(State.CONNECTING)
        log.info("connecting to %s", url)
        self._timer.start(self._connect_timeout_ms)
        ws.open(QNetworkRequest(QUrl(url)), opts)

    def close(self) -> None:
        """Polite close (sends a WebSocket close frame so PTT frees the session promptly)."""
        self._intentional_close = True
        self._timer.stop()
        if self._ws is not None:
            self._ws.close()
        if self.state is State.CONNECTING:
            self._set_state(State.DISCONNECTED)

    def send(self, data: bytes) -> bool:
        """Send raw terminal bytes. Returns False (and sends nothing) unless connected."""
        if self.state is not State.CONNECTED or self._ws is None or not data:
            return False
        self._ws.sendBinaryMessage(data)
        self.bytes_sent += len(data)  # only counts; the content is never logged
        return True

    # ----------------------------------------------------------------- slots
    def _on_connected(self) -> None:
        self._timer.stop()
        self._set_state(State.CONNECTED)
        log.info("connected (subprotocol=%r)", self._ws.subprotocol() if self._ws else "")

    def _on_message(self, data) -> None:
        data = bytes(data)
        if self._first:
            self._first = False
            if data.startswith(_PROXY_PREFIX):
                data = data[len(_PROXY_PREFIX):]
        self.bytes_received += len(data)
        data = self._iac.feed(data)
        if data:
            self.dataReceived.emit(data)

    def _on_error(self, err) -> None:
        if self._intentional_close:
            return
        msg = self._ws.errorString() if self._ws else str(err)
        log.warning("socket error: %s", msg)
        self._timer.stop()
        self.failed.emit(f"連線錯誤：{msg}")
        if self.state is State.CONNECTING and self._ws is not None:   # handshake failed: no 'disconnected' follows
            self._intentional_close = True
            self._ws.abort()
            self._set_state(State.DISCONNECTED)

    def _on_disconnected(self) -> None:
        self._timer.stop()
        was = self.state
        ws, self._ws = self._ws, None
        if ws is not None:
            ws.deleteLater()
        self._set_state(State.DISCONNECTED)
        if was is State.CONNECTED and not self._intentional_close:
            log.warning("connection lost by remote")
            self.failed.emit("連線已中斷（伺服器關閉連線）。程式不會自動重連或重送任何內容。")

    def _on_connect_timeout(self) -> None:
        log.warning("connect timeout")
        self.failed.emit(f"連線逾時（{self._connect_timeout_ms // 1000} 秒）。")
        self._intentional_close = True
        if self._ws is not None:
            self._ws.abort()
        self._set_state(State.DISCONNECTED)

    def _set_state(self, st: State) -> None:
        if st is not self.state:
            self.state = st
            self.stateChanged.emit(st)
