import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox

from conftest import wait_until
from src.net.client import State
from src.net.poster import Target
from src.net.session import PttSession
from src.storage.db import Database
from src.ui.main_window import MainWindow


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    db = Database(tmp_path / "locks.db")
    window = MainWindow(db, PttSession())
    yield window
    window.session.disconnect_()
    db.close()


def make_ready(window):
    window.session.client.state = State.CONNECTED
    window.session.logged_in = True
    window._on_conn_state(State.CONNECTED)
    window.chk_confirm.setChecked(True)
    window.board_combo.setEditText("Gossiping")
    window._sync_board_fav_button()
    window._update_type_buttons()


def test_paste_disables_typing_login_and_board_then_restores(win):
    make_ready(win)
    assert win.btn_type_title.isEnabled() and win.btn_type_body.isEnabled()
    assert win.btn_login.isEnabled() and win.btn_board_go.isEnabled()

    win.term._set_pasting(True)
    assert not win.btn_type_title.isEnabled()
    assert not win.btn_type_body.isEnabled()
    assert not win.btn_login.isEnabled()
    assert not win.btn_board_go.isEnabled()
    assert "\u8cbc\u4e0a\u9032\u884c\u4e2d" in win.statusBar().currentMessage()

    win.term._set_pasting(False)
    assert win.btn_type_title.isEnabled() and win.btn_type_body.isEnabled()
    assert win.btn_login.isEnabled() and win.btn_board_go.isEnabled()


def test_paste_refuses_login_board_and_typing_even_when_called_directly(win, monkeypatch):
    make_ready(win)
    win.term._set_pasting(True)
    login_calls, sends, typing_calls = [], [], []
    monkeypatch.setattr(win.session, "login", lambda *a: login_calls.append(a) or True)
    monkeypatch.setattr(win.session, "send_user_bytes", lambda data: sends.append(data) or True)
    monkeypatch.setattr(win, "run_checks", lambda: typing_calls.append("checks") or [])
    monkeypatch.setattr(win, "save_draft", lambda: typing_calls.append("save") or 1)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked"))))

    win.account.setText("user")
    win.password.setText("pw")
    win._do_login()
    assert login_calls == []
    assert win.password.text() == ""
    assert "\u5df2\u66ab\u505c\u767b\u5165" in win.statusBar().currentMessage()

    win.goto_board()
    assert sends == []
    assert "\u5df2\u66ab\u505c\u524d\u5f80\u770b\u677f" in win.statusBar().currentMessage()

    win.type_into_ptt(Target.TITLE)
    assert typing_calls == []
    assert "\u5df2\u66ab\u505c\u8f38\u5165" in win.statusBar().currentMessage()
    assert "\u8cbc\u4e0a\u9032\u884c\u4e2d" in win.type_status.text()


def test_paste_restore_keeps_login_disabled_when_offline(win):
    make_ready(win)
    win.term._set_pasting(True)
    win.session.client.state = State.DISCONNECTED
    win._on_conn_state(State.DISCONNECTED)
    win.term._set_pasting(False)
    assert not win.btn_login.isEnabled()
    assert not win.btn_type_title.isEnabled()


def test_real_paste_start_and_finish_toggle_the_controls(win, monkeypatch):
    make_ready(win)
    sent = []
    monkeypatch.setattr(win.term.s.client, "send", lambda data: sent.append(bytes(data)) or True)
    QGuiApplication.clipboard().setText("hello")
    assert win.term.paste_from_clipboard()
    assert not win.btn_type_title.isEnabled()
    assert not win.btn_login.isEnabled()
    assert not win.btn_board_go.isEnabled()
    assert wait_until(lambda: not win.term.pasting)
    assert win.btn_type_title.isEnabled()
    assert win.btn_login.isEnabled()
    assert win.btn_board_go.isEnabled()
    assert b"".join(sent) == b"hello"
