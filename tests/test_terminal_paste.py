from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from conftest import pump, wait_until
from src.net.client import State
from src.net.paster import MAX_PASTE_CHARS, PasteSender, paste_preview, paste_stats, sanitize_paste
from src.net.session import PttSession
from src.ui.terminal_widget import TerminalWidget


def make_term(*lines: str, connected: bool = True) -> TerminalWidget:
    term = TerminalWidget(PttSession())
    term.resize(720, 480)
    term.s.screen.feed(("\r\n".join(lines)).encode("cp950"))
    term._refresh_links()
    term.show()
    QApplication.processEvents()
    if connected:
        term.s.client.state = State.CONNECTED
    return term


def record_sends(monkeypatch, term):
    sent = []
    monkeypatch.setattr(term.s.client, "send", lambda data: sent.append(bytes(data)) or True)
    return sent


def collect_notices(term):
    out = []
    term.notice.connect(out.append)
    return out


def test_sanitize_normalises_newlines_tabs_and_controls():
    clean, removed = sanitize_paste("a\tb\x1b[31mC\r\nD\rE\x07")
    assert clean == "a    b[31mC\nD\nE"
    assert removed == 2


def test_paste_stats_and_preview():
    assert paste_stats("hello\nworld") == (10, 2)
    assert paste_stats("") == (0, 1)
    preview = paste_preview("1\n2\n3\n4\n5\n6")
    assert preview.startswith("1\n2\n3\n4\n5\n")
    assert "\u5176\u9918 1 \u884c" in preview
    assert len(paste_preview("x" * 150).split("\n")[0]) <= 101


def test_sender_chunks_and_turns_newlines_into_cr(qapp, monkeypatch):
    session = PttSession()
    session.client.state = State.CONNECTED
    sent = []
    monkeypatch.setattr(session.client, "send", lambda data: sent.append(bytes(data)) or True)
    text = "a" * 250 + "\n" + "b" * 50
    done = []
    paster = PasteSender(session, lambda: None)
    paster.finished.connect(lambda ok, msg: done.append((ok, msg)))
    assert paster.start(text) is None
    assert wait_until(lambda: not paster.running)
    assert b"".join(sent) == text.replace("\n", "\r").encode("cp950")
    assert len(sent) > 1
    assert all(len(chunk) <= 100 for chunk in sent)
    assert paster.chars_sent == len(text) - 1
    assert done and done[-1][0] is True
    assert "\u8cbc\u4e0a\u5b8c\u6210" in done[-1][1]


def test_sender_stops_for_good_when_connection_drops(qapp, monkeypatch):
    session = PttSession()
    session.client.state = State.CONNECTED
    sent = []
    monkeypatch.setattr(session.client, "send", lambda data: sent.append(bytes(data)) or True)
    done = []
    paster = PasteSender(session, lambda: None)
    paster.finished.connect(lambda ok, msg: done.append((ok, msg)))
    assert paster.start("a" * 1000) is None
    assert len(sent) == 1
    session.client.state = State.DISCONNECTED
    session.client.stateChanged.emit(State.DISCONNECTED)
    assert not paster.running
    assert done and done[-1][0] is False
    assert "\u5df2\u9001\u51fa" in done[-1][1]
    count = len(sent)
    pump(300)
    assert len(sent) == count


def test_sender_stops_when_guard_reports_locked(qapp, monkeypatch):
    session = PttSession()
    session.client.state = State.CONNECTED
    sent = []
    monkeypatch.setattr(session.client, "send", lambda data: sent.append(bytes(data)) or True)
    blocked = [False]
    done = []
    paster = PasteSender(session, lambda: "\u81ea\u52d5\u8f38\u5165\u9032\u884c\u4e2d\u3002" if blocked[0] else None)
    paster.finished.connect(lambda ok, msg: done.append((ok, msg)))
    assert paster.start("a" * 1000) is None
    blocked[0] = True
    assert wait_until(lambda: not paster.running)
    assert len(sent) < 10
    assert done and done[-1][0] is False
    assert "\u81ea\u52d5\u8f38\u5165" in done[-1][1]


def test_sender_refuses_when_disconnected(qapp, monkeypatch):
    session = PttSession()
    sent = []
    monkeypatch.setattr(session.client, "send", lambda data: sent.append(bytes(data)) or True)
    paster = PasteSender(session, lambda: None)
    why = paster.start("hello")
    assert why and "\u5c1a\u672a\u9023\u7dda" in why
    assert sent == []


def test_paste_refused_when_not_connected(qapp):
    term = make_term(connected=False)
    notices = collect_notices(term)
    QGuiApplication.clipboard().setText("hello")
    assert not term.paste_from_clipboard()
    assert notices and "\u5c1a\u672a\u9023\u7dda" in notices[-1]


def test_paste_refused_while_terminal_is_locked(qapp, monkeypatch):
    term = make_term()
    sent = record_sends(monkeypatch, term)
    notices = collect_notices(term)
    term.locked = True
    QGuiApplication.clipboard().setText("hello")
    assert not term.paste_from_clipboard()
    assert sent == []
    assert notices and "\u81ea\u52d5\u8f38\u5165" in notices[-1]


def test_paste_refuses_unencodable_characters_without_partial_send(qapp, monkeypatch):
    term = make_term()
    sent = record_sends(monkeypatch, term)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2]) or QMessageBox.StandardButton.Ok))
    QGuiApplication.clipboard().setText("ok\U0001F600")
    assert not term.paste_from_clipboard()
    assert sent == []
    assert warnings and "Big5" in warnings[-1]
    assert "\U0001F600" in warnings[-1]


def test_paste_refuses_more_than_limit(qapp, monkeypatch):
    term = make_term()
    sent = record_sends(monkeypatch, term)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2]) or QMessageBox.StandardButton.Ok))
    QGuiApplication.clipboard().setText("a" * (MAX_PASTE_CHARS + 1))
    assert not term.paste_from_clipboard()
    assert sent == []
    assert warnings and str(MAX_PASTE_CHARS) in warnings[-1]


def test_short_single_line_paste_is_sent_without_confirmation(qapp, monkeypatch):
    term = make_term()
    sent = record_sends(monkeypatch, term)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked"))))
    QGuiApplication.clipboard().setText("hello")
    assert term.paste_from_clipboard()
    assert wait_until(lambda: not term._paster.running)
    assert b"".join(sent) == b"hello"


def test_multiline_paste_previews_and_sends_cr(qapp, monkeypatch):
    term = make_term()
    sent = record_sends(monkeypatch, term)
    questions = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: questions.append(a[2]) or QMessageBox.StandardButton.Yes))
    QGuiApplication.clipboard().setText("line1\nline2")
    notices = collect_notices(term)
    assert term.paste_from_clipboard()
    assert wait_until(lambda: not term._paster.running)
    assert questions and "10" in questions[0] and "2" in questions[0]
    assert b"".join(sent) == b"line1\rline2"
    assert notices and "\u8cbc\u4e0a\u5b8c\u6210" in notices[-1]


def test_paste_preview_cancel_sends_nothing(qapp, monkeypatch):
    term = make_term()
    sent = record_sends(monkeypatch, term)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))
    notices = collect_notices(term)
    QGuiApplication.clipboard().setText("one\ntwo")
    assert not term.paste_from_clipboard()
    assert sent == []
    assert notices and "\u5df2\u53d6\u6d88" in notices[-1]


def test_paste_filters_controls_and_tabs(qapp, monkeypatch):
    term = make_term()
    sent = record_sends(monkeypatch, term)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    QGuiApplication.clipboard().setText("a\tb\x1b[31mC\r\nD\rE")
    assert term.paste_from_clipboard()
    assert wait_until(lambda: not term._paster.running)
    assert b"".join(sent) == "a    b[31mC\rD\rE".encode("cp950")


def test_ctrl_v_still_sends_0x16(qapp, monkeypatch):
    term = make_term()
    sent = []
    monkeypatch.setattr(term.s, "send_user_bytes", lambda data: sent.append(bytes(data)) or True)
    called = []
    monkeypatch.setattr(term, "paste_from_clipboard", lambda: called.append(True))
    term.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key_V, Qt.KeyboardModifier.ControlModifier))
    assert sent == [b"\x16"]
    assert called == []


def test_ctrl_shift_v_pastes_and_sends_no_key_bytes(qapp, monkeypatch):
    term = make_term()
    sent = []
    monkeypatch.setattr(term.s, "send_user_bytes", lambda data: sent.append(bytes(data)) or True)
    called = []
    monkeypatch.setattr(term, "paste_from_clipboard", lambda: called.append(True))
    term.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key_V,
                                 Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
    assert called == [True]
    assert sent == []


def test_keys_are_paused_while_pasting(qapp, monkeypatch):
    term = make_term()
    sent = []
    monkeypatch.setattr(term.s, "send_user_bytes", lambda data: sent.append(bytes(data)) or True)
    notices = collect_notices(term)
    term.pasting = True
    term.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key_A, Qt.KeyboardModifier.NoModifier, "a"))
    assert sent == []
    assert notices and "\u8cbc\u4e0a\u9032\u884c\u4e2d" in notices[-1]


def test_context_menu_has_paste_action(qapp, monkeypatch):
    term = make_term()
    called = []
    monkeypatch.setattr(term, "paste_from_clipboard", lambda: called.append(True))
    menu = term._build_context_menu()
    assert menu.actions()[-1].text() == "\u8cbc\u4e0a"
    menu.actions()[-1].trigger()
    assert called == [True]


def test_paste_stops_when_locked_midway(qapp, monkeypatch):
    term = make_term()
    sent = record_sends(monkeypatch, term)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    notices = collect_notices(term)
    QGuiApplication.clipboard().setText("a" * 1000)
    assert term.paste_from_clipboard()
    term.locked = True
    assert wait_until(lambda: not term._paster.running)
    assert "\u81ea\u52d5\u8f38\u5165" in notices[-1]
    assert 0 < len(sent) < 10
