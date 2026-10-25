"""Optional SOCKS5 / HTTP proxy for the BBS connection only.

The proxy is supplied by the user (for example a local SSH tunnel or a VPN client
that exposes a SOCKS5 port).  Nothing here bundles, discovers or rotates proxies:
the configured endpoint is dialled for the BBS socket and nowhere else.  Article
fetches, update checks, image downloads and uploads keep their own pinned
connections and never use this proxy.

Credentials are intentionally *not* persisted by this module.  The UI keeps the
proxy password in memory for the running session only.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtNetwork import QNetworkProxy

KINDS = (("none", "不使用（直連）"), ("socks5", "SOCKS5"), ("http", "HTTP"))
KIND_KEYS = tuple(key for key, _label in KINDS)
KIND_LABELS = dict(KINDS)
DEFAULT_PORTS = {"socks5": 1080, "http": 8080}
MAX_USER = 128
MAX_PASSWORD = 256


@dataclass(frozen=True)
class ProxyConfig:
    """A validated-on-use proxy endpoint.  ``kind == "none"`` means a direct connection."""

    kind: str = "none"
    host: str = ""
    port: int = 0
    user: str = ""
    password: str = ""

    def __repr__(self) -> str:
        """Never expose the password through repr()/debug output."""
        secret = "'***'" if self.password else "''"
        return (f"ProxyConfig(kind={self.kind!r}, host={self.host!r}, port={self.port!r}, "
                f"user={self.user!r}, password={secret})")

    def problem(self) -> str | None:
        """A user-facing reason the config cannot be used, or None."""
        if self.kind == "none":
            return None
        if self.kind not in ("socks5", "http"):
            return "代理類型不受支援。"
        host = self.host.strip()
        if not host:
            return "請輸入代理主機。"
        if len(host) > 255 or any(ch.isspace() or ord(ch) < 32 for ch in host):
            return "代理主機含有空白或控制字元。"
        if "://" in host or "/" in host or "\\" in host or "@" in host:
            return "代理主機只填主機名稱或 IP，不要含 scheme、路徑或帳密。"
        try:
            port = int(self.port)
        except (TypeError, ValueError):
            return "代理連接埠必須是數字。"
        if not 1 <= port <= 65535:
            return "代理連接埠必須介於 1 到 65535。"
        if len(self.user) > MAX_USER or len(self.password) > MAX_PASSWORD:
            return "代理帳號或密碼過長。"
        if any(ord(ch) < 32 for ch in self.user + self.password):
            return "代理帳號或密碼含有控制字元。"
        return None

    @property
    def enabled(self) -> bool:
        return self.kind != "none"

    @property
    def endpoint(self) -> str:
        host = self.host.strip()
        if ":" in host and not host.startswith("["):       # bare IPv6
            host = f"[{host}]"
        return f"{host}:{self.port}" if host else ""

    def label(self) -> str:
        """Log/status text that never includes the username or password."""
        return f"{KIND_LABELS.get(self.kind, self.kind)} {self.endpoint}".strip()

    def to_qt(self) -> QNetworkProxy | None:
        """Qt proxy object, or None for a direct connection.  Raises ValueError when invalid."""
        problem = self.problem()
        if problem:
            raise ValueError(problem)
        if not self.enabled:
            return None
        kind = (QNetworkProxy.ProxyType.Socks5Proxy if self.kind == "socks5"
                else QNetworkProxy.ProxyType.HttpProxy)
        return QNetworkProxy(kind, self.host.strip(), int(self.port), self.user, self.password)
