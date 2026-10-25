import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkProxy
from PySide6.QtWidgets import QMessageBox

from src.net import client as cmod
from src.net.client import PttClient, State
from src.net.proxy import ProxyConfig
from src.net.session import PttSession
from src.storage.db import Database
from src.ui.main_window import MainWindow


def test_direct_connection_has_no_qt_proxy():
    config = ProxyConfig()
    assert config.problem() is None
    assert not config.enabled
    assert config.to_qt() is None


@pytest.mark.parametrize("config, text", [
    (ProxyConfig("socks5", "", 1080), "代理主機"),
    (ProxyConfig("socks5", "http://proxy.test", 1080), "scheme"),
    (ProxyConfig("socks5", "proxy.test", 0), "連接埠"),
    (ProxyConfig("socks5", "proxy.test", 70000), "連接埠"),
    (ProxyConfig("unknown", "proxy.test", 1080), "類型"),
    (ProxyConfig("socks5", "proxy.test", 1080, "u\x00", ""), "控制字元"),
])
def test_invalid_proxy_is_refused(config, text):
    problem = config.problem()
    assert problem and text in problem
    with pytest.raises(ValueError):
        config.to_qt()


def test_proxy_types_and_credentials_map_to_qt():
    socks = ProxyConfig("socks5", "127.0.0.1", 1080, "user", "pa55").to_qt()
    assert socks.type() == QNetworkProxy.ProxyType.Socks5Proxy
    assert (socks.hostName(), socks.port(), socks.user(), socks.password()) == ("127.0.0.1", 1080, "user", "pa55")
    http = ProxyConfig("http", "proxy.example", 8080).to_qt()
    assert http.type() == QNetworkProxy.ProxyType.HttpProxy
    assert (http.hostName(), http.port()) == ("proxy.example", 8080)


def test_label_and_repr_never_contain_password():
    config = ProxyConfig("socks5", "127.0.0.1", 1080, "alice", "s3cret")
    assert config.label() == "SOCKS5 127.0.0.1:1080"
    assert "alice" not in config.label() and "s3cret" not in config.label()
    assert "s3cret" not in repr(config) and "***" in repr(config)


class _FakeWS(QObject):
    connected = Signal()
    disconnected = Signal()
    errorOccurred = Signal(object)
    binaryMessageReceived = Signal(bytes)
    textMessageReceived = Signal(str)

    def __init__(self, origin):
        super().__init__()
        self.origin = origin
        self.proxy = None
        self.opened = None

    def setProxy(self, proxy):
        self.proxy = proxy

    def setMaxAllowedIncomingFrameSize(self, _size):
        pass

    def setMaxAllowedIncomingMessageSize(self, _size):
        pass

    def open(self, request, options):
        self.opened = (request, options)

    def abort(self):
        pass

    def deleteLater(self):
        pass

    def subprotocol(self):
        return "binary"


class _FakeTCP(QObject):
    connected = Signal()
    readyRead = Signal()
    disconnected = Signal()
    errorOccurred = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proxy = None
        self.target = None

    def setProxy(self, proxy):
        self.proxy = proxy

    def connectToHost(self, host, port):
        self.target = (host, port)

    def abort(self):
        pass

    def deleteLater(self):
        pass


def test_wss_socket_receives_proxy_before_open(monkeypatch):
    monkeypatch.setattr(cmod, "QWebSocket", _FakeWS)
    client = PttClient()
    client.connect_to("wss://ws.ptt.cc/bbs", ProxyConfig("socks5", "127.0.0.1", 1080, "u", "p"))
    try:
        ws = client._ws
        assert ws is not None and ws.opened is not None
        assert ws.proxy.type() == QNetworkProxy.ProxyType.Socks5Proxy
        assert (ws.proxy.hostName(), ws.proxy.port()) == ("127.0.0.1", 1080)
        assert client.state is State.CONNECTING
    finally:
        client.close()


def test_telnet_socket_receives_proxy_before_connect(monkeypatch):
    monkeypatch.setattr(cmod, "QTcpSocket", _FakeTCP)
    client = PttClient()
    client.connect_to("telnet://ptt.cc:23", ProxyConfig("http", "proxy.example", 8080))
    try:
        tcp = client._tcp
        assert tcp is not None and tcp.target == ("ptt.cc", 23)
        assert tcp.proxy.type() == QNetworkProxy.ProxyType.HttpProxy
        assert (tcp.proxy.hostName(), tcp.proxy.port()) == ("proxy.example", 8080)
    finally:
        client.close()


def test_invalid_proxy_refuses_to_connect(monkeypatch):
    made = []
    monkeypatch.setattr(cmod, "QWebSocket", lambda origin: made.append(origin) or _FakeWS(origin))
    client = PttClient()
    failed = []
    client.failed.connect(failed.append)
    client.connect_to("wss://ws.ptt.cc/bbs", ProxyConfig("socks5", "", 1080))
    assert not made and client.state is State.DISCONNECTED
    assert failed and "代理設定無效" in failed[-1]


@pytest.fixture
def win(qapp, tmp_path):
    db = Database(tmp_path / "proxy.db")
    window = MainWindow(db, PttSession())
    yield window
    window.session.disconnect_()
    db.close()


def test_ui_proxy_round_trip_does_not_store_password(win, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a[2]) or QMessageBox.StandardButton.Ok))
    win.proxy_kind.setCurrentIndex(win.proxy_kind.findData("socks5"))
    win.proxy_host.setText("127.0.0.1")
    win.proxy_port.setValue(1080)
    win.proxy_user.setText("alice")
    win.proxy_password.setText("s3cret")
    config = win._proxy_config()
    assert config == ProxyConfig("socks5", "127.0.0.1", 1080, "alice", "s3cret")
    assert not warned
    assert win.db.get_setting("proxy.kind") == "socks5"
    assert win.db.get_setting("proxy.host") == "127.0.0.1"
    assert win.db.get_setting("proxy.user") == "alice"
    assert win.db.get_setting("proxy.password", "") == ""
    assert win.lbl_proxy.text() == "代理：SOCKS5 127.0.0.1:1080"


def test_ui_invalid_proxy_blocks_connect(win, monkeypatch):
    warned = []
    calls = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a[1]) or QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(win.session, "connect_to", lambda url, proxy=None: calls.append((url, proxy)))
    win.proxy_kind.setCurrentIndex(win.proxy_kind.findData("socks5"))
    win.proxy_host.setText("")
    assert not win._connect_bbs("wss://ws.ptt.cc/bbs")
    assert warned and "代理設定" in warned[-1]
    assert not calls


def test_ui_connect_passes_proxy_snapshot(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win.session, "connect_to", lambda url, proxy=None: calls.append((url, proxy)))
    win.proxy_kind.setCurrentIndex(win.proxy_kind.findData("socks5"))
    win.proxy_host.setText("127.0.0.1")
    win.proxy_port.setValue(1080)
    assert win._connect_bbs("wss://ws.ptt.cc/bbs")
    url, proxy = calls[-1]
    assert url == "wss://ws.ptt.cc/bbs"
    assert proxy == ProxyConfig("socks5", "127.0.0.1", 1080, "", "")
