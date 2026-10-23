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


def test_iac_filter_strips_and_answers_negotiation():
    f = IacFilter()
    data, replies = f.feed_with_replies(b"A\xff\xfb\x01B\xff\xfd\x03C")
    assert data == b"ABC"
    assert replies == b"\xff\xfe\x01\xff\xfc\x03"


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
