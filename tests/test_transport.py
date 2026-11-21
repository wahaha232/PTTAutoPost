from PySide6.QtCore import QObject, Signal

from src.net import transport as T
from src.net.transport import TelnetTransport


class FakeTCP(QObject):
    connected = Signal()
    readyRead = Signal()
    disconnected = Signal()
    errorOccurred = Signal(object)
    bytesWritten = Signal(int)

    def __init__(self, results=None):
        super().__init__()
        self.results = list(results or [])
        self.writes = []
        self.accepted = bytearray()
        self.flushes = 0
        self.aborted = False

    def setProxy(self, _proxy):
        pass

    def connectToHost(self, host, port):
        self.target = (host, port)

    def write(self, data):
        self.writes.append(bytes(data))
        n = self.results.pop(0) if self.results else len(data)
        if n > 0:
            self.accepted.extend(data[:n])
        return n

    def flush(self):
        self.flushes += 1

    def abort(self):
        self.aborted = True

    def deleteLater(self):
        pass

    def readAll(self):
        return b""

    def errorString(self):
        return "boom"


def _telnet(fake):
    return TelnetTransport(None, "bbs.example", 23, None, lambda _parent: fake)


def test_full_write_accepts_the_whole_chunk():
    fake = FakeTCP()
    t = _telnet(fake)
    assert t.send(b"abc") is True
    assert bytes(fake.accepted) == b"abc"


def test_partial_write_keeps_the_remainder_in_order():
    fake = FakeTCP([1])
    t = _telnet(fake)
    assert t.send(b"abc") is True
    assert t._pending == b"bc"
    fake.bytesWritten.emit(1)
    assert bytes(fake.accepted) == b"abc"
    assert not t._pending


def test_write_failure_is_reported_and_not_queued():
    fake = FakeTCP([-1])
    t = _telnet(fake)
    assert t.send(b"abc") is False
    assert not t._pending


def test_multiple_chunks_are_flushed_in_order():
    fake = FakeTCP([1, 1, 1, 1, 1])
    t = _telnet(fake)
    assert t.send(b"abc") is True
    assert t.send(b"de") is True
    assert t._pending == b"bcde"
    fake.bytesWritten.emit(1)
    assert bytes(fake.accepted) == b"abcde"
    assert not t._pending


def test_disconnect_during_pending_write_clears_the_queue():
    fake = FakeTCP([1])
    t = _telnet(fake)
    assert t.send(b"abc") is True
    closed = []
    t.closed.connect(closed.append)
    fake.disconnected.emit()
    assert closed and "中斷" in closed[-1]
    assert not t._pending
    fake.bytesWritten.emit(1)                             # late signal must not resend anything
    assert bytes(fake.accepted) == b"a"


def test_close_clears_pending_and_ignores_delayed_signals():
    fake = FakeTCP([1])
    t = _telnet(fake)
    assert t.send(b"abc") is True
    t.close()
    fake.bytesWritten.emit(1)
    assert bytes(fake.accepted) == b"a"
    assert not t._pending


class FakeWS(QObject):
    connected = Signal()
    disconnected = Signal()
    errorOccurred = Signal(object)
    binaryMessageReceived = Signal(bytes)
    textMessageReceived = Signal(str)

    def __init__(self, result):
        super().__init__()
        self.result = result

    def setProxy(self, _proxy):
        pass

    def setMaxAllowedIncomingFrameSize(self, _n):
        pass

    def setMaxAllowedIncomingMessageSize(self, _n):
        pass

    def open(self, *_args):
        pass

    def sendBinaryMessage(self, data):
        return self.result if self.result is not None else len(data)

    def abort(self):
        pass

    def deleteLater(self):
        pass


def test_websocket_uses_whole_message_semantics():
    ok = T.WebSocketTransport(None, "wss://ws.ptt.cc/bbs", "https://term.ptt.cc", None,
                              lambda _origin: FakeWS(None))
    assert ok.send(b"abc") is True
    refused = T.WebSocketTransport(None, "wss://ws.ptt.cc/bbs", "https://term.ptt.cc", None,
                                   lambda _origin: FakeWS(0))
    assert refused.send(b"abc") is False


class FakeProc(QObject):
    started = Signal()
    readyReadStandardOutput = Signal()
    readyReadStandardError = Signal()
    errorOccurred = Signal(object)
    finished = Signal(int, object)
    bytesWritten = Signal(int)

    class ProcessChannelMode:
        SeparateChannels = 0

    def __init__(self, results=None):
        super().__init__()
        self.results = list(results or [])
        self.accepted = bytearray()
        self.blocks = []

    def setProcessEnvironment(self, _env):
        pass

    def setProcessChannelMode(self, _mode):
        pass

    def start(self, _program, _args):
        pass

    def write(self, data):
        n = self.results.pop(0) if self.results else len(data)
        if n > 0:
            self.accepted.extend(data[:n])
        return n

    def readAllStandardOutput(self):
        return b""

    def readAllStandardError(self):
        return b""

    def errorString(self):
        return "boom"

    def blockSignals(self, flag):
        self.blocks.append(flag)

    def kill(self):
        pass

    def deleteLater(self):
        pass


def test_ssh_uses_the_same_buffered_write_path(monkeypatch):
    fake = FakeProc([2])

    class ProcFactory:
        ProcessChannelMode = FakeProc.ProcessChannelMode

        def __call__(self, _parent):
            return fake

    monkeypatch.setattr(T, "QProcess", ProcFactory())
    monkeypatch.setattr(T.shutil, "which", lambda _name: "ssh.exe")
    t = T.SshTransport(None, "ptt.cc", "bbs", 22, 10000)
    assert t.send(b"abcd") is True
    assert t._pending == b"cd"
    fake.bytesWritten.emit(2)
    assert bytes(fake.accepted) == b"abcd"
    assert not t._pending
