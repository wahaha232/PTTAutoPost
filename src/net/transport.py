"""Lightweight transports for the three PTT protocols.

Each transport owns exactly one socket/process and exposes the same four signals:
`opened`, `data`, `errorOccurred` and `closed`.  `PttClient` therefore no longer needs a
separate `_stale*` / `_drop_*` / `_intentional_close` guard for every protocol: it keeps one
current transport and ignores signals whose sender is not that transport.

Transports never retry and never reconnect; they only report what happened.
"""
from __future__ import annotations

import shutil

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QUrl, Signal
from PySide6.QtNetwork import QNetworkRequest

from ..logging_setup import get_logger
from .telnet import IacFilter

log = get_logger("net")


class Transport(QObject):
    """One connection attempt.  Signals are always protocol-agnostic."""

    opened = Signal()
    data = Signal(bytes)
    errorOccurred = Signal(str)
    closed = Signal(str)             # reason shown when the peer closes during/before connect

    decoded = False                  # True when data is already filtered for the client

    def __init__(self, parent=None):
        super().__init__(parent)
        self._closing = False

    @property
    def socket(self):
        return None

    def open(self) -> None:
        raise NotImplementedError

    def send(self, data: bytes) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        self._closing = True


class WebSocketTransport(Transport):
    def __init__(self, parent, url: str, origin: str, proxy, socket_cls):
        super().__init__(parent)
        self._url = url
        self._opts = None
        ws = socket_cls(origin)
        if proxy is not None:
            ws.setProxy(proxy)                             # must be set before open()
        ws.setMaxAllowedIncomingFrameSize(256 * 1024)      # PTT frames are a few KB; refuse absurd ones
        ws.setMaxAllowedIncomingMessageSize(1024 * 1024)
        self._socket = ws
        ws.connected.connect(self._on_connected)
        ws.disconnected.connect(self._on_disconnected)
        ws.errorOccurred.connect(self._on_error)
        ws.binaryMessageReceived.connect(self._on_message)
        ws.textMessageReceived.connect(
            lambda _s: log.warning("ignored an unexpected text frame (PTT sends binary only)"))

    @property
    def socket(self):
        return self._socket

    def open(self) -> None:
        from PySide6.QtWebSockets import QWebSocketHandshakeOptions
        opts = QWebSocketHandshakeOptions()
        opts.setSubprotocols(["binary"])
        self._opts = opts                                   # keep a reference for the handshake
        self._socket.open(QNetworkRequest(QUrl(self._url)), opts)

    def send(self, data: bytes) -> bool:
        sock = self._socket
        if self._closing or sock is None:
            return False
        return sock.sendBinaryMessage(data) == len(data)    # Qt returns the bytes queued (0 when refused)

    def close(self) -> None:
        self._closing = True
        sock, self._socket = self._socket, None
        if sock is not None:
            sock.abort()
            sock.deleteLater()

    def _on_connected(self) -> None:
        if not self._closing:
            self.opened.emit()

    def _on_message(self, data) -> None:
        if not self._closing:
            self.data.emit(bytes(data))

    def _on_error(self, err) -> None:
        if self._closing:
            return
        msg = self._socket.errorString() if self._socket is not None else str(err)
        self.errorOccurred.emit(f"WSS 連線錯誤：{msg}")

    def _on_disconnected(self) -> None:
        if not self._closing:
            self.closed.emit("WSS 連線中斷（伺服器關閉連線）。")


class TelnetTransport(Transport):
    decoded = True                                       # IAC is stripped (and answered) here

    def __init__(self, parent, host: str, port: int, proxy, socket_cls):
        super().__init__(parent)
        self._host, self._port = host, port
        self._iac = IacFilter()
        tcp = socket_cls(parent)
        if proxy is not None:
            tcp.setProxy(proxy)                            # must be set before connectToHost()
        self._socket = tcp
        tcp.connected.connect(self._on_connected)
        tcp.readyRead.connect(self._on_ready)
        tcp.disconnected.connect(self._on_disconnected)
        tcp.errorOccurred.connect(self._on_error)

    @property
    def socket(self):
        return self._socket

    def open(self) -> None:
        log.info("connecting telnet to %s:%s (plaintext)", self._host, self._port)
        self._socket.connectToHost(self._host, self._port)

    def send(self, data: bytes) -> bool:
        sock = self._socket
        if self._closing or sock is None or sock.write(data) < 0:
            return False
        sock.flush()
        return True

    def close(self) -> None:
        self._closing = True
        sock, self._socket = self._socket, None
        if sock is not None:
            sock.abort()
            sock.deleteLater()

    def _on_connected(self) -> None:
        if not self._closing:
            self.opened.emit()

    def _on_ready(self) -> None:
        sock = self._socket
        if self._closing or sock is None:
            return
        data = bytes(sock.readAll())
        if not data:
            return
        data, replies = self._iac.feed_with_replies(data)
        if replies:
            sock.write(replies)
            sock.flush()
        if data:
            self.data.emit(data)

    def _on_error(self, err) -> None:
        sock = self._socket
        if self._closing or sock is None:
            return
        msg = sock.errorString() if hasattr(sock, "errorString") else str(err)
        self.errorOccurred.emit(f"Telnet 連線錯誤：{msg}")

    def _on_disconnected(self) -> None:
        if not self._closing:
            self.closed.emit("Telnet 連線中斷（伺服器關閉連線）。")


class SshTransport(Transport):
    def __init__(self, parent, host: str, user: str, port: int, connect_timeout_ms: int):
        super().__init__(parent)
        self._host, self._user, self._port = host, user, port
        self._connect_timeout_ms = connect_timeout_ms
        self._stderr = b""
        self._opened = False
        self._ssh = shutil.which("ssh")
        self._socket = None
        if self._ssh:
            proc = QProcess(self)
            env = QProcessEnvironment.systemEnvironment()
            env.insert("TERM", "xterm-256color")
            proc.setProcessEnvironment(env)
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
            self._socket = proc
            proc.started.connect(self._on_started)
            proc.readyReadStandardOutput.connect(self._on_ready)
            proc.readyReadStandardError.connect(self._on_stderr)
            proc.errorOccurred.connect(self._on_error)
            proc.finished.connect(self._on_finished)

    @property
    def socket(self):
        return self._socket

    def open(self) -> None:
        if self._socket is None:
            self.errorOccurred.emit("找不到系統 SSH 用戶端（ssh.exe），無法使用 SSH 連線。")
            return
        log.info("connecting ssh to %s@%s:%s", self._user, self._host, self._port)
        self._socket.start(self._ssh, [
            "-tt",                                     # force a remote PTY even though stdin/stdout are pipes
            "-o", "BatchMode=yes",                     # PTT uses "none" auth; never wait for an invisible prompt
            "-o", "StrictHostKeyChecking=accept-new",  # first use is trusted, later changes are refused
            "-o", f"ConnectTimeout={max(1, self._connect_timeout_ms // 1000)}",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-p", str(self._port),
            f"{self._user}@{self._host}",
        ])

    def send(self, data: bytes) -> bool:
        sock = self._socket
        if self._closing or sock is None:
            return False
        return sock.write(data) >= 0

    def close(self) -> None:
        self._closing = True
        proc, self._socket = self._socket, None
        if proc is not None:
            proc.blockSignals(True)                    # its late signals must not touch a newer connection
            proc.kill()
            proc.deleteLater()

    def _on_started(self) -> None:
        log.info("ssh process started; waiting for the BBS screen")

    def _on_stderr(self) -> None:
        sock = self._socket
        if self._closing or sock is None:
            return
        data = bytes(sock.readAllStandardError())
        if data:
            self._stderr = (self._stderr + data)[-4096:]   # diagnostics only; never shown as terminal data

    def _on_ready(self) -> None:
        sock = self._socket
        if self._closing or sock is None:
            return
        data = bytes(sock.readAllStandardOutput())
        if not data:
            return
        if not self._opened:
            self._opened = True
            self.opened.emit()
        self.data.emit(data)

    def _on_error(self, err) -> None:
        sock = self._socket
        if self._closing or sock is None:
            return
        msg = sock.errorString() or str(err)
        self.errorOccurred.emit(f"SSH 連線錯誤：{msg}")

    def _on_finished(self, code: int, _status) -> None:
        if self._closing:
            return
        if not self._opened:
            detail = self._stderr.decode("utf-8", "replace").strip().splitlines()
            tail = detail[-1][:300] if detail else ""
            self.errorOccurred.emit(f"SSH 連線失敗：{tail}" if tail else f"SSH 連線失敗（結束碼 {code}）。")
            return
        self.closed.emit("SSH 連線中斷（SSH 連線結束）。")
