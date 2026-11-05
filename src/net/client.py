"""Transports to PTT: WSS (Qt), Telnet (Qt) and SSH (the OpenSSH client).

Facts verified against the live WSS endpoint on 2026-10-15 (tools/probe_wss.py):
* `wss://ws.ptt.cc/bbs` completes the handshake only when an `Origin: https://term.ptt.cc`
  header is sent (HTTP 403 without it). Sub-protocol is optional; "binary" is accepted.
* The very first message begins with the literal text "HTTP/1.1 200 OK\\r\\n\\r\\n" (proxy header)
  followed by the login screen (Big5 + ANSI). That prefix is stripped here.
* The server ends the login screen with "請輸入代號，或以 guest 參觀，或以 new 註冊:".

The PTT SSH endpoint (`ssh bbs@ptt.cc`) authenticates with "none", allocates a PTY and
prints the same BBS login screen, including the same HTTP/1.1 prefix.  It is served by
the system OpenSSH client (ssh.exe on Windows), so no extra Python dependency is needed.

When an initial connection to the official PTT/PTT2 WebSocket endpoint fails, the client
automatically retries the matching SSH endpoint once (and the other way round).  A session
that was already established is reported once and is NEVER reconnected or resent.
"""
from __future__ import annotations

import enum
import shutil
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest, QTcpSocket
from PySide6.QtWebSockets import QWebSocket, QWebSocketHandshakeOptions

from ..logging_setup import get_logger
from .proxy import ProxyConfig
from .telnet import IacFilter

log = get_logger("net")
DEFAULT_URL = "wss://ws.ptt.cc/bbs"
ORIGIN = "https://term.ptt.cc"
_PROXY_PREFIX = b"HTTP/1.1 200 OK\r\n\r\n"
TRUSTED_LOGIN_HOSTS = ("ws.ptt.cc",)          # the assisted login only ever sends credentials to these hosts
_LOOPBACK = ("127.0.0.1", "localhost", "::1")
DEFAULT_SSH_USER = "bbs"
# Explicit pairs only: a failed official WSS endpoint may use the matching SSH endpoint,
# and vice versa.  Nothing else is tried, so an arbitrary host is never dialled behind
# the user's back.
FALLBACK_URLS = {
    "wss://ws.ptt.cc/bbs": "ssh://bbs@ptt.cc:22",
    "wss://ws.ptt2.cc/bbs": "ssh://bbs@ptt2.cc:22",
    "ssh://bbs@ptt.cc:22": "wss://ws.ptt.cc/bbs",
    "ssh://bbs@ptt2.cc:22": "wss://ws.ptt2.cc/bbs",
}


def fallback_url(url: str) -> str | None:
    """The other protocol for the same site, or None when this endpoint has no pair."""
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        port = p.port
        if p.scheme == "wss":
            if host not in ("ws.ptt.cc", "ws.ptt2.cc") or port not in (None, 443):
                return None
            if (p.path or "/") != "/bbs" or p.username or p.password:
                return None
            return FALLBACK_URLS[f"wss://ws.{host[3:]}/bbs"]
        if p.scheme == "ssh":
            if host not in ("ptt.cc", "ptt2.cc") or port not in (None, 22) or p.password:
                return None
            if (p.username or DEFAULT_SSH_USER).lower() != "bbs" or (p.path or ""):
                return None
            return FALLBACK_URLS[f"ssh://bbs@{host}:22"]
    except ValueError:
        return None
    return None


def protocol_label(url: str) -> str:
    scheme = (urlparse(url).scheme or "").lower() if url else ""
    return {"wss": "WSS", "ssh": "SSH", "telnet": "Telnet"}.get(scheme, scheme.upper() or "未知")


def endpoint_problem(url: str) -> str | None:
    """Reason a BBS endpoint is refused, or None. wss/ws(loopback), telnet or ssh; no passwords."""
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        host = p.hostname
        port = p.port
    except ValueError:
        return "端點網址格式錯誤。"
    if not host:
        return "端點缺少主機名稱。"
    if p.password:
        return "端點網址不可包含密碼。"
    if p.username and p.scheme != "ssh":
        return "只有 SSH 端點可以包含帳號。"
    if p.scheme == "ssh":
        if (p.path or "") not in ("", "/") or p.query or p.fragment:
            return "SSH 端點不使用路徑、查詢字串或片段。"
        if port is not None and not 1 <= port <= 65535:
            return "SSH 連接埠需在 1～65535。"
        user = p.username or DEFAULT_SSH_USER
        if not (user.isascii() and 1 <= len(user) <= 64
                and all(ch.isalnum() or ch in "._-" for ch in user)):
            return "SSH 帳號格式不正確。"
        return None
    if p.scheme == "wss" or (p.scheme == "ws" and host in _LOOPBACK):
        return None
    if p.scheme == "telnet" and (port is None or 1 <= port <= 65535):
        return None
    return "端點必須使用 wss://、telnet:// 或 ssh://（ws:// 僅限本機測試）。"


def origin_for(url: str) -> str:
    """Origin header a BBS web bridge expects: its web terminal page (ws.X -> https://term.X).

    Verified 2026-10-22: ws.ptt.cc needs term.ptt.cc and ws.ptt2.cc needs term.ptt2.cc (403 otherwise).
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ORIGIN
    if not host or host in _LOOPBACK:
        return ORIGIN                                      # local fake BBS used by the tests
    if host.startswith("ws."):
        return f"https://term.{host[3:]}"
    return f"https://{host}"


def login_host_trusted(url: str) -> bool:
    """True only for the exact official endpoint (or a local test endpoint).

    A suffix match is not enough: a crafted host such as ws.ptt.cc.evil.example must
    never receive the user's credentials, and neither should another port or path.
    """
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
    except ValueError:
        return False
    if host in _LOOPBACK:
        return True                                        # local fake BBS used by the tests
    if p.scheme == "ssh":
        return (host == "ptt.cc" and (p.username or DEFAULT_SSH_USER).lower() == "bbs"
                and p.port in (None, 22) and not p.password and (p.path or "") == "")
    return (p.scheme == "wss" and host in TRUSTED_LOGIN_HOSTS and p.port in (None, 443)
            and (p.path or "/") in ("/", "/bbs") and not p.username and not p.password)


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
        self._tcp: QTcpSocket | None = None
        self._ssh: QProcess | None = None
        self._ssh_err = b""
        self.url = DEFAULT_URL
        self._first = True
        self._head = b""
        self._fallback: str | None = None
        self._intentional_close = False
        self._connect_timeout_ms = connect_timeout_ms
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_connect_timeout)
        self.bytes_sent = 0
        self.bytes_received = 0
        self._iac = IacFilter()
        self.proxy = ProxyConfig()

    # ----------------------------------------------------------------- control
    def set_proxy(self, proxy: ProxyConfig) -> None:
        """Use this proxy for the next BBS connection (WSS and Telnet).  SSH uses ssh.exe and ignores it."""
        self.proxy = proxy

    def connect_to(self, url: str = DEFAULT_URL, proxy: ProxyConfig | None = None) -> None:
        if self.state is not State.DISCONNECTED:
            return
        if proxy is not None:
            self.proxy = proxy
        problem = endpoint_problem(url)
        if problem:
            log.warning("endpoint refused: %s", problem)
            self.failed.emit(problem)
            return
        proxy_problem = self.proxy.problem()
        if proxy_problem:
            log.warning("proxy refused: %s", proxy_problem)
            self.failed.emit(f"代理設定無效：{proxy_problem}")
            return
        # ssh.exe cannot use the configured SOCKS5/HTTP proxy; never bypass an explicit proxy
        # by silently switching to a direct SSH connection.
        self._fallback = fallback_url(url) if not self.proxy.enabled else None
        self._start_connect(url)

    def _start_connect(self, url: str) -> None:
        """Begin one transport attempt; _fallback is kept until it is used or the first data arrives."""
        self.url = url
        self._first, self._intentional_close, self._head = True, False, b""
        self.bytes_sent = self.bytes_received = 0
        self._iac = IacFilter()
        self._drop_ws()                                    # never leave a previous socket without an owner
        self._drop_tcp()
        self._drop_ssh()
        parsed = urlparse(url)
        if parsed.scheme == "telnet":
            self._connect_telnet(parsed.hostname or "", parsed.port or 23)
            return
        if parsed.scheme == "ssh":
            self._connect_ssh(parsed)
            return
        ws = QWebSocket(origin_for(url))
        qt_proxy = self.proxy.to_qt()
        if qt_proxy is not None:
            ws.setProxy(qt_proxy)                             # must be set before open()
            log.info("BBS connection uses %s", self.proxy.label())
        ws.setMaxAllowedIncomingFrameSize(256 * 1024)         # PTT frames are a few KB; refuse absurd ones
        ws.setMaxAllowedIncomingMessageSize(1024 * 1024)
        self._ws = ws
        ws.connected.connect(self._on_connected)
        ws.disconnected.connect(self._on_disconnected)
        ws.errorOccurred.connect(self._on_error)
        ws.binaryMessageReceived.connect(self._on_message)
        ws.textMessageReceived.connect(lambda _s: log.warning("ignored an unexpected text frame (PTT sends binary only)"))
        opts = QWebSocketHandshakeOptions()
        opts.setSubprotocols(["binary"])
        self._set_state(State.CONNECTING)
        log.info("connecting to %s", url)
        self._timer.start(self._connect_timeout_ms)
        ws.open(QNetworkRequest(QUrl(url)), opts)

    def close(self) -> None:
        """Drop the socket and report DISCONNECTED immediately.

        Waiting for the peer's disconnected signal left the client in CONNECTED after a
        half-closed TCP session, so connect_to() refused to start a new connection.  The
        connection is aborted on purpose: the user explicitly asked to disconnect and an
        immediate reconnect must always be possible.
        """
        self._intentional_close = True
        self._fallback = None
        self._timer.stop()
        self._drop_ws()
        self._drop_tcp()
        self._drop_ssh()
        self._set_state(State.DISCONNECTED)

    def _drop_ws(self) -> None:
        """Single cleanup path: forget the current socket, abort it and let Qt delete it."""
        ws, self._ws = self._ws, None
        if ws is not None:
            ws.abort()
            ws.deleteLater()

    def _drop_tcp(self) -> None:
        tcp, self._tcp = self._tcp, None
        if tcp is not None:
            tcp.abort()
            tcp.deleteLater()

    def _drop_ssh(self) -> None:
        """Stop ssh.exe without letting its late signals touch a newer connection."""
        proc, self._ssh = self._ssh, None
        if proc is not None:
            proc.blockSignals(True)
            proc.kill()
            proc.deleteLater()

    def _connect_telnet(self, host: str, port: int) -> None:
        tcp = QTcpSocket(self)
        qt_proxy = self.proxy.to_qt()
        if qt_proxy is not None:
            tcp.setProxy(qt_proxy)                            # must be set before connectToHost()
            log.info("BBS connection uses %s", self.proxy.label())
        self._tcp = tcp
        tcp.connected.connect(self._on_tcp_connected)
        tcp.readyRead.connect(self._on_tcp_ready)
        tcp.disconnected.connect(self._on_tcp_disconnected)
        tcp.errorOccurred.connect(self._on_tcp_error)
        self._set_state(State.CONNECTING)
        log.info("connecting telnet to %s:%s (plaintext)", host, port)
        self._timer.start(self._connect_timeout_ms)
        tcp.connectToHost(host, port)

    def _connect_ssh(self, parsed) -> None:
        self._set_state(State.CONNECTING)
        ssh = shutil.which("ssh")
        if not ssh:
            self._connect_failed("找不到系統 SSH 用戶端（ssh.exe），無法使用 SSH 連線。")
            return
        host = parsed.hostname or ""
        user = parsed.username or DEFAULT_SSH_USER
        port = parsed.port or 22
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "xterm-256color")
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._ssh, self._ssh_err = proc, b""
        proc.started.connect(self._on_ssh_started)
        proc.readyReadStandardOutput.connect(self._on_ssh_ready)
        proc.readyReadStandardError.connect(self._on_ssh_stderr)
        proc.errorOccurred.connect(self._on_ssh_error)
        proc.finished.connect(self._on_ssh_finished)
        log.info("connecting ssh to %s@%s:%s", user, host, port)
        self._timer.start(self._connect_timeout_ms)
        proc.start(ssh, [
            "-tt",                                     # force a remote PTY even though stdin/stdout are pipes
            "-o", "BatchMode=yes",                     # PTT uses "none" auth; never wait for an invisible prompt
            "-o", "StrictHostKeyChecking=accept-new",  # first use is trusted, later changes are refused
            "-o", f"ConnectTimeout={max(1, self._connect_timeout_ms // 1000)}",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-p", str(port),
            f"{user}@{host}",
        ])

    def _stale(self) -> bool:
        """True for a signal from a socket that is no longer the current one (it must never touch the current state)."""
        s = self.sender()
        return s is not None and s is not self._ws

    def send(self, data: bytes) -> bool:
        """Send raw terminal bytes. Returns False (and sends nothing) unless connected."""
        if self.state is not State.CONNECTED or not data:
            return False
        if self._tcp is not None:
            if self._tcp.write(data) < 0:
                return False
            self._tcp.flush()
        elif self._ssh is not None:
            if self._ssh.write(data) < 0:
                return False
        elif self._ws is not None:
            if self._ws.sendBinaryMessage(data) != len(data):    # Qt returns the bytes queued (0 when it refused)
                return False
        else:
            return False
        self.bytes_sent += len(data)  # only counts; the content is never logged
        return True

    # ----------------------------------------------------------------- slots
    def _on_connected(self) -> None:
        if self._stale():
            return
        if self._intentional_close or self.state is not State.CONNECTING:      # cancelled / timed out meanwhile
            if self._ws is not None:
                self._ws.abort()
            return
        self._timer.stop()
        self._fallback = None                              # an established session is never swapped or retried
        self._set_state(State.CONNECTED)
        log.info("connected (subprotocol=%r)", self._ws.subprotocol() if self._ws else "")

    def _on_message(self, data) -> None:
        data = bytes(data)
        if self._first:                                    # the proxy status line may be split across frames: buffer until decided
            data = self._head + data
            if len(data) < len(_PROXY_PREFIX) and _PROXY_PREFIX.startswith(data):
                self._head = data
                return
            self._head, self._first = b"", False
            if data.startswith(_PROXY_PREFIX):
                data = data[len(_PROXY_PREFIX):]
        self.bytes_received += len(data)
        data = self._iac.feed(data)
        if data:
            self.dataReceived.emit(data)

    def _stale_tcp(self) -> bool:
        s = self.sender()
        return s is not None and s is not self._tcp

    def _on_tcp_connected(self) -> None:
        if self._stale_tcp():
            return
        if self._intentional_close or self.state is not State.CONNECTING:
            self._drop_tcp()
            return
        self._timer.stop()
        self._fallback = None
        self._set_state(State.CONNECTED)
        log.info("connected (telnet)")

    def _on_tcp_ready(self) -> None:
        if self._stale_tcp() or self._tcp is None:
            return
        data = bytes(self._tcp.readAll())
        if not data:
            return
        self.bytes_received += len(data)
        data, replies = self._iac.feed_with_replies(data)
        if replies and self._tcp is not None:
            self._tcp.write(replies)
            self._tcp.flush()
        if data:
            self.dataReceived.emit(data)

    def _on_tcp_error(self, _err) -> None:
        if self._intentional_close or self._stale_tcp() or self._tcp is None:
            return
        msg = self._tcp.errorString()
        log.warning("telnet socket error: %s", msg)
        if self.state is State.CONNECTING:
            self._connect_failed(f"Telnet 連線錯誤：{msg}")
        else:
            self._timer.stop()
            self.failed.emit(f"連線錯誤：{msg}")

    def _on_tcp_disconnected(self) -> None:
        if self._stale_tcp():
            return
        was = self.state
        if was is State.CONNECTING and not self._intentional_close:
            self._connect_failed("Telnet 連線中斷（伺服器關閉連線）。")
            return
        self._timer.stop()
        self._drop_tcp()
        self._set_state(State.DISCONNECTED)
        if was is State.CONNECTED and not self._intentional_close:
            log.warning("telnet connection lost by remote")
            self.failed.emit("連線已中斷（伺服器關閉連線）。程式不會自動重連或重送任何內容。")

    def _on_error(self, err) -> None:
        if self._intentional_close or self._stale():
            return
        msg = self._ws.errorString() if self._ws else str(err)
        log.warning("socket error: %s", msg)
        if self.state is State.CONNECTING and self._ws is not None:   # handshake failed: no 'disconnected' follows
            self._connect_failed(f"WSS 連線錯誤：{msg}")
        else:
            self._timer.stop()
            self.failed.emit(f"連線錯誤：{msg}")

    def _on_disconnected(self) -> None:
        if self._stale():
            return
        was = self.state
        if was is State.CONNECTING and not self._intentional_close:
            self._connect_failed("WSS 連線中斷（伺服器關閉連線）。")
            return
        self._timer.stop()
        ws, self._ws = self._ws, None
        if ws is not None:
            ws.deleteLater()
        self._set_state(State.DISCONNECTED)
        if was is State.CONNECTED and not self._intentional_close:
            log.warning("connection lost by remote")
            self.failed.emit("連線已中斷（伺服器關閉連線）。程式不會自動重連或重送任何內容。")

    def _connect_failed(self, reason: str) -> None:
        """End a failed initial attempt; switch to the paired protocol once, if there is one."""
        if self._intentional_close or self.state is not State.CONNECTING:
            return
        alt, self._fallback = self._fallback, None
        self._timer.stop()
        self._intentional_close = True
        self._drop_ws()
        self._drop_tcp()
        self._drop_ssh()
        self._set_state(State.DISCONNECTED)
        if alt:
            log.warning("initial %s connection failed; switching to %s", protocol_label(self.url), protocol_label(alt))
            self.failed.emit(f"{reason} 自動改用 {protocol_label(alt)} 連線…")
            self._intentional_close = False
            self._start_connect(alt)
        else:
            self.failed.emit(reason)

    def _on_connect_timeout(self) -> None:
        log.warning("connect timeout")
        self._connect_failed(f"連線逾時（{self._connect_timeout_ms // 1000} 秒）。")

    # ----------------------------------------------------------------- ssh (OpenSSH)
    def _stale_ssh(self) -> bool:
        s = self.sender()
        return s is not None and s is not self._ssh

    def _on_ssh_started(self) -> None:
        if not self._stale_ssh():
            log.info("ssh process started; waiting for the BBS screen")

    def _on_ssh_stderr(self) -> None:
        if self._stale_ssh() or self._ssh is None:
            return
        data = bytes(self._ssh.readAllStandardError())
        if data:
            self._ssh_err = (self._ssh_err + data)[-4096:]     # diagnostics only; never shown as terminal data

    def _on_ssh_ready(self) -> None:
        if self._stale_ssh() or self._ssh is None:
            return
        data = bytes(self._ssh.readAllStandardOutput())
        if not data:
            return
        if self.state is State.CONNECTING and not self._intentional_close:
            self._timer.stop()
            self._fallback = None
            self._set_state(State.CONNECTED)
            log.info("connected (ssh)")
        self._on_message(data)

    def _on_ssh_error(self, err) -> None:
        if self._intentional_close or self._stale_ssh() or self._ssh is None:
            return
        msg = self._ssh.errorString() or str(err)
        log.warning("ssh process error: %s", msg)
        if self.state is State.CONNECTING:
            self._connect_failed(f"SSH 連線錯誤：{msg}")

    def _on_ssh_finished(self, code: int, _status) -> None:
        if self._stale_ssh():
            return
        if self._intentional_close:
            self._drop_ssh()
            return
        was = self.state
        detail = self._ssh_err.decode("utf-8", "replace").strip().splitlines()
        tail = detail[-1][:300] if detail else ""
        if was is State.CONNECTING:
            self._connect_failed(f"SSH 連線失敗：{tail}" if tail else f"SSH 連線失敗（結束碼 {code}）。")
            return
        self._drop_ssh()
        if was is State.CONNECTED:
            log.warning("ssh connection lost")
            self._set_state(State.DISCONNECTED)
            self.failed.emit("連線已中斷（SSH 連線結束）。程式不會自動重連或重送任何內容。")

    def _set_state(self, st: State) -> None:
        if st is not self.state:
            self.state = st
            self.stateChanged.emit(st)
