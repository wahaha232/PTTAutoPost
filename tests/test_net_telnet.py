from PySide6.QtNetwork import QTcpServer

from conftest import pump, wait_until
from src.net.client import PttClient, State, endpoint_problem
from src.net.telnet import IacFilter


def test_endpoint_allows_telnet_but_not_credentials():
    assert endpoint_problem("telnet://bbs.example.com:23") is None
    assert endpoint_problem("telnet://bbs.example.com") is None
    assert endpoint_problem("telnet://user:pass@bbs.example.com:23")
    assert endpoint_problem("http://bbs.example.com")
    assert endpoint_problem("wss://ws.ptt.cc/bbs") is None


def test_failed_initial_connection_switches_protocol_once(qapp):
    client = PttClient()
    starts, failed = [], []
    client._start_connect = starts.append
    client.failed.connect(failed.append)
    client._fallback = "ssh://bbs@ptt.cc:22"
    client._set_state(State.CONNECTING)
    client._connect_failed("WSS 連線錯誤：拒絕連線")
    assert starts == ["ssh://bbs@ptt.cc:22"]
    assert failed and "自動改用 SSH" in failed[-1]
    assert client.state is State.DISCONNECTED

    client._set_state(State.CONNECTING)
    client._connect_failed("SSH 連線錯誤：逾時")
    assert starts == ["ssh://bbs@ptt.cc:22"]                 # only one switch, never a loop
    assert failed[-1] == "SSH 連線錯誤：逾時"
    client.close()


def test_iac_filter_strips_and_answers_negotiation():
    f = IacFilter()
    data, replies = f.feed_with_replies(b"A\xff\xfb\x01B\xff\xfd\x03C")
    assert data == b"ABC"
    assert replies == b"\xff\xfe\x01\xff\xfc\x03"


def test_plain_feed_matches_the_reply_parser_output():
    payload = b"A\xff\xfb\x01B\xff\xfa\x01x\xff\xf0C\xff\xffD"
    assert IacFilter().feed(payload) == IacFilter().feed_with_replies(payload)[0]


def test_telnet_transport_connects_sends_and_receives(qapp):
    server = QTcpServer()
    assert server.listen()
    port = server.serverPort()
    client = PttClient()
    states, received = [], []
    client.stateChanged.connect(states.append)
    client.dataReceived.connect(received.append)
    client.connect_to(f"telnet://127.0.0.1:{port}")
    assert wait_until(lambda: client.state is State.CONNECTED, 5000)
    assert wait_until(lambda: server.hasPendingConnections(), 2000)
    sock = server.nextPendingConnection()
    sock.write(b"\xff\xfb\x01hello")
    sock.flush()
    assert wait_until(lambda: b"hello" in b"".join(received), 3000)
    assert client.send(b"abc")
    buf = bytearray()

    def read_client_bytes():
        buf.extend(bytes(sock.readAll()))
        return b"abc" in buf

    assert wait_until(read_client_bytes, 3000)
    client.close()
    assert wait_until(lambda: client.state is State.DISCONNECTED, 3000)
    assert State.CONNECTED in states and states[-1] is State.DISCONNECTED
    pump(20)
