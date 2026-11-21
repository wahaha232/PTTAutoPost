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

The protocol-specific socket/process handling lives in `transport.py`; this module is
responsible for endpoint validation, proxy selection, the connect timeout and the single
wss/ssh fallback.
"""
from __future__ import annotations

import enum
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QTcpSocket
from PySide6.QtWebSockets import QWebSocket

from ..logging_setup import get_logger
from .proxy import ProxyConfig
from .telnet import IacFilter
from .transport import SshTransport, TelnetTransport, Transport, WebSocketTransport

log = get_logger("net")
DEFAULT_URL = "wss://ws.ptt.cc/bbs"
ORIGIN = "https://term.ptt.cc"
_PROXY_PREFIX = b"HTTP/1.1 200 OK\r\n\r\n"
TRUSTED_LOGIN_HOSTS = ("ws.ptt.cc",)          # the assisted login only ever sends credentials to these hosts
# Telnet sites with no encrypted entrance; the password is plaintext either way (typed by hand or not).
TRUSTED_TELNET_LOGINS = {("bbs.gamer.com.tw", 23)}
_LOOPBACK = ("127.0.0.1", "localhost", "::1")
DEFAULT_SSH_USER = "bbs"


def fallback_url(url: str) -> str | None:
    """The other official protocol for the same site, or None for anything else.

    Only the exact official endpoints are paired (ws.ptt.cc <-> ssh ptt.cc, and the ptt2
    equivalents).  A custom port, another path, userinfo, a query/fragment or any other
    host is refused, so an arbitrary address is never dialled behind the user's back.
    """
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        port = p.port
    except ValueError:
        return None
    if p.password or p.query or p.fragment:
        return None
    if p.scheme == "wss":
        if host not in ("ws.ptt.cc", "ws.ptt2.cc") or port not in (None, 443):
            return None
        if p.username or (p.path or "/") != "/bbs":
            return None
        return f"ssh://bbs@{host[3:]}:22"
    if p.scheme == "ssh":
        if host not in ("ptt.cc", "ptt2.cc") or port not in (None, 22):
            return None
        if (p.username or DEFAULT_SSH_USER).lower() != "bbs" or (p.path or ""):
            return None
        return f"wss://ws.{host}/bbs"
    return None


def protocol_label(url: str) -> str:
    scheme = (urlparse(url).scheme or "").lower() if url else ""
    return {"wss": "WSS", "ssh": "SSH", "telnet": "Telnet"}.get(scheme, scheme.upper() or "未知")


def endpoint_problem(url: str) -> str | None:
    """Reason a BBS endpoint is refused, or None. wss/ws(loopback), telnet or ssh; no passwords."""
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
    """True only for an exact official endpoint (PTT WSS/SSH, Bahamut Telnet) or a local test endpoint.

    A suffix match is not enough: a crafted host such as ws.ptt.cc.evil.example must
    never receive the user's credentials, and neither should another port or path.
    """
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
    except ValueError:
        return False
    if host in _LOOPBACK:
        return True                                        # local fake BBS used by the tests
    if p.scheme == "telnet":
        try:
            port = p.port or 23
        except ValueError:
            return False
        return ((host, port) in TRUSTED_TELNET_LOGINS and not p.username and not p.password
                and (p.path or "") in ("", "/"))
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
        self._transport: Transport | None = None
        self.url = DEFAULT_URL
        self._first = True
        self._head = b""
        self._fallback: str | None = None
        self._connect_timeout_ms = connect_timeout_ms
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_connect_timeout)
        self.bytes_sent = 0
        self.bytes_received = 0
        self._iac = IacFilter()
        self.proxy = ProxyConfig()
        self.host_key_check = None                     # set by the UI: (host, port) -> (ok, reason)
        self.ssh_known_hosts_path = None               # project-owned file, never the user's ~/.ssh

    @property
    def _ws(self):
        """The raw WSS socket of the current attempt (test/introspection only)."""
        t = self._transport
        return t.socket if isinstance(t, WebSocketTransport) else None

    @property
    def _tcp(self):
        """The raw Telnet socket of the current attempt (test/introspection only)."""
        t = self._transport
        return t.socket if isinstance(t, TelnetTransport) else None

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
        self._first, self._head = True, b""
        self.bytes_sent = self.bytes_received = 0
        self._iac = IacFilter()
        self._drop_transport()                             # never leave a previous transport without an owner
        parsed = urlparse(url)
        qt_proxy = None
        if parsed.scheme != "ssh":
            qt_proxy = self.proxy.to_qt()
            if qt_proxy is not None:
                log.info("BBS connection uses %s", self.proxy.label())
        if parsed.scheme == "telnet":
            transport = TelnetTransport(self, parsed.hostname or "", parsed.port or 23, qt_proxy, QTcpSocket)
        elif parsed.scheme == "ssh":
            transport = SshTransport(self, parsed.hostname or "", parsed.username or DEFAULT_SSH_USER,
                                     parsed.port or 22, self._connect_timeout_ms,
                                     host_key_check=self.host_key_check,
                                     known_hosts_path=self.ssh_known_hosts_path)
        else:
            transport = WebSocketTransport(self, url, origin_for(url), qt_proxy, QWebSocket)
        self._transport = transport
        transport.opened.connect(self._on_transport_opened)
        transport.data.connect(self._on_transport_data)
        transport.errorOccurred.connect(self._on_transport_error)
        transport.closed.connect(self._on_transport_closed)
        self._set_state(State.CONNECTING)
        log.info("connecting to %s", url)
        transport.open()                     # SSH may wait for the host-key confirmation dialog
        if self._transport is transport and self.state is State.CONNECTING:
            self._timer.start(self._connect_timeout_ms)

    def close(self) -> None:
        """Drop the socket and report DISCONNECTED immediately.

        Waiting for the peer's disconnected signal left the client in CONNECTED after a
        half-closed TCP session, so connect_to() refused to start a new connection.  The
        connection is aborted on purpose: the user explicitly asked to disconnect and an
        immediate reconnect must always be possible.
        """
        self._fallback = None
        self._timer.stop()
        self._drop_transport()
        self._set_state(State.DISCONNECTED)

    def _drop_transport(self) -> None:
        """Forget the current transport first: its late signals can no longer touch this client."""
        transport, self._transport = self._transport, None
        if transport is not None:
            transport.close()
            transport.deleteLater()

    def send(self, data: bytes) -> bool:
        """Send raw terminal bytes. Returns False (and sends nothing) unless connected."""
        if self.state is not State.CONNECTED or not data:
            return False
        transport = self._transport
        if transport is None or not transport.send(data):
            return False
        self.bytes_sent += len(data)  # only counts; the content is never logged
        return True

    # ----------------------------------------------------------------- slots
    def _on_transport_opened(self) -> None:
        if self.sender() is not self._transport:
            return
        self._timer.stop()
        self._fallback = None                              # an established session is never swapped or retried
        self._set_state(State.CONNECTED)
        log.info("connected (%s)", protocol_label(self.url))

    def _on_transport_data(self, data: bytes) -> None:
        transport = self._transport
        if transport is None or self.sender() is not transport:
            return
        if transport.decoded:                              # Telnet already stripped/answered IAC
            self.bytes_received += len(data)
            if data:
                self.dataReceived.emit(data)
        else:
            self._on_message(data)

    def _on_transport_error(self, msg: str) -> None:
        if self.sender() is not self._transport:
            return
        log.warning("transport error: %s", msg)
        if self.state is State.CONNECTING:
            self._connect_failed(msg, allow_fallback=not msg.startswith("SSH 主機金鑰驗證失敗"))
        else:
            self._timer.stop()
            self.failed.emit(msg)

    def _on_transport_closed(self, reason: str) -> None:
        if self.sender() is not self._transport:
            return
        was = self.state
        self._timer.stop()
        if was is State.CONNECTING:
            self._connect_failed(reason)
            return
        self._drop_transport()
        self._set_state(State.DISCONNECTED)
        if was is State.CONNECTED:
            log.warning("connection lost by remote")
            self.failed.emit(f"{reason} 程式不會自動重連或重送任何內容。")

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

    def _connect_failed(self, reason: str, allow_fallback: bool = True) -> None:
        """End a failed initial attempt; switch to the paired protocol once, if allowed."""
        if self.state is not State.CONNECTING:
            return
        alt = self._fallback if allow_fallback else None
        self._fallback = None
        self._timer.stop()
        self._drop_transport()
        self._set_state(State.DISCONNECTED)
        if alt:
            log.warning("initial %s connection failed; switching to %s", protocol_label(self.url), protocol_label(alt))
            self.failed.emit(f"{reason} 自動改用 {protocol_label(alt)} 連線…")
            self._start_connect(alt)
        else:
            self.failed.emit(reason)

    def _on_connect_timeout(self) -> None:
        log.warning("connect timeout")
        self._connect_failed(f"連線逾時（{self._connect_timeout_ms // 1000} 秒）。")

    def _set_state(self, st: State) -> None:
        if st is not self.state:
            self.state = st
            self.stateChanged.emit(st)
