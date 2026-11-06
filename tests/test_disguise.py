from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from src.net.client import State
from src.net.session import PttSession
from src.storage.db import Database
from src.ui.disguise import DISGUISE_TITLE
from src.ui.main_window import MainWindow


def make_window(tmp_path, name="disguise.db"):
    db = Database(tmp_path / name)
    return MainWindow(db, PttSession()), db


def press(term, key, modifiers=Qt.KeyboardModifier.NoModifier):
    term.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers))


def test_disguise_uses_the_live_notepad_terminal_and_hides_the_app(qapp, tmp_path):
    win, db = make_window(tmp_path)
    win.session.screen.feed("測試文章 https://example.test/a.png\r\n".encode("cp950"))
    win.session.screenChanged.emit()

    win.set_disguise(True)

    assert win.windowTitle() == DISGUISE_TITLE
    assert win._central_stack.currentWidget() is win.disguise_terminal
    assert win.term.parent() is win.disguise_terminal
    assert win.term.notepad and win.term.cursor_style == "bar"
    assert not win.term.links_enabled
    assert [menu.title() for menu in win._fake_menus] == ["檔案(F)", "編輯(E)", "格式(O)", "說明(H)"]
    assert win.statusBar().isHidden()
    assert db.get_setting("ui.disguise") == "1"

    win.set_disguise(False)

    assert win._central_stack.currentWidget() is win.tabs
    assert win.term.parent() is not win.disguise_terminal
    assert not win.term.notepad and win.term.cursor_style == "outline"
    assert win.term.links_enabled
    assert win.windowTitle() != DISGUISE_TITLE
    assert not win.statusBar().isHidden()
    db.close()


def test_disguise_keeps_browsing_and_posting_keys_working(qapp, tmp_path, monkeypatch):
    win, db = make_window(tmp_path)
    win.session.screen.feed("PTT 畫面\r\n".encode("cp950"))
    win.session.screenChanged.emit()
    win.session.client.state = State.CONNECTED
    sent = []
    monkeypatch.setattr(win.session, "send_user_bytes", lambda data: sent.append(data) or True)

    win.set_disguise(True)
    press(win.term, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)   # Ctrl+P: PTT post editor
    press(win.term, Qt.Key.Key_Down)                                    # browse

    assert sent == [b"\x10", b"\x1b[B"]
    win.set_disguise(False)
    db.close()


def test_disguise_shows_the_open_article_while_offline(qapp, tmp_path):
    win, db = make_window(tmp_path)
    win._set_article_panel_visible(True)
    win.w["post_title"].setText("[新聞] 測試標題")
    win.body.setPlainText("這是文章內文")
    win.notes.setPlainText("這是個人心得")

    win.set_disguise(True)

    assert win._central_stack.currentWidget() is win.disguise_view
    assert win.disguise_view.editor.isReadOnly()
    text = win.disguise_view.text()
    assert "[新聞] 測試標題" in text and "這是文章內文" in text and "這是個人心得" in text
    assert "（目前沒有可顯示的文字）" not in text
    win.set_disguise(False)
    db.close()


def test_disguise_switches_to_the_live_terminal_when_the_connection_arrives(qapp, tmp_path):
    win, db = make_window(tmp_path)
    win.body.setPlainText("離線文章")
    win.set_disguise(True)
    assert win._central_stack.currentWidget() is win.disguise_view

    win.session.client.state = State.CONNECTED
    win.session.screen.feed("PTT 連線畫面\r\n".encode("cp950"))
    win.session.screenChanged.emit()

    assert win._central_stack.currentWidget() is win.disguise_terminal
    assert win.term.parent() is win.disguise_terminal
    win.set_disguise(False)
    db.close()


def test_disguise_shows_a_plain_text_notice_when_there_is_nothing_to_read(qapp, tmp_path):
    win, db = make_window(tmp_path)
    win.set_disguise(True)
    assert win._central_stack.currentWidget() is win.disguise_view
    assert win.disguise_view.text() == "（目前沒有可顯示的文字）"
    win.set_disguise(False)
    db.close()


def test_disguise_blocks_images_links_and_hover_preview(qapp, tmp_path, monkeypatch):
    win, db = make_window(tmp_path)
    opened = []
    monkeypatch.setattr("src.ui.browser.open_url",
                        lambda *a, **k: (opened.append(a), (True, "ok"))[1])
    win.chk_auto_image.setChecked(True)
    win.session.client.state = State.CONNECTED
    win.set_disguise(True)
    win.session.screen.feed("https://example.test/a.png\r\n".encode("cp950"))
    win.session.screenChanged.emit()
    win._on_links_changed(win.term.links())
    win._on_link_hovered("https://example.test/a.png")

    assert not win.term.links_enabled
    assert win._open_link("https://example.test/") is False
    assert win._open_image_inside("https://example.test/a.png") is False
    assert win._open_article_images(["https://example.test/a.png"]) is False
    assert win._open_sponsor() is False
    assert not opened
    assert win._image_viewer is None
    assert not win._hover_timer.isActive()

    win.set_disguise(False)
    assert win._central_stack.currentWidget() is win.tabs
    assert win.windowTitle() != DISGUISE_TITLE
    assert db.get_setting("ui.disguise") == "0"
    assert not win.statusBar().isHidden()
    db.close()


def test_disguise_shortcut_toggles_and_mode_is_remembered(qapp, tmp_path):
    path = tmp_path / "remember.db"
    db = Database(path)
    win = MainWindow(db, PttSession())
    win.act_disguise.trigger()
    assert win._disguise and win.chk_disguise.isChecked()
    win.act_disguise.trigger()
    assert not win._disguise and not win.chk_disguise.isChecked()
    win.set_disguise(True)
    db.close()

    db2 = Database(path)
    win2 = MainWindow(db2, PttSession())
    assert win2._disguise
    assert win2.chk_disguise.isChecked()
    assert win2.term.notepad and not win2.term.links_enabled
    win2.act_disguise.trigger()
    assert not win2._disguise and not win2.term.notepad and win2.term.links_enabled
    db2.close()
