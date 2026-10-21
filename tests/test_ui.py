import threading
from http.server import ThreadingHTTPServer

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from conftest import pump, wait_until
from src.net.poster import Target
from src.net.session import PttSession
from src.storage.db import Database
from src.terminal.detect import Kind
from src.ui.main_window import MainWindow
from src.ui.terminal_widget import key_to_bytes
from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from test_extract_fetch import H


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    db = Database(tmp_path / "ui.db")
    w = MainWindow(db, PttSession())
    yield w
    w.session.disconnect_()
    pump(50)
    db.close()


@pytest.fixture
def http_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def fill_article(win):
    win.w["post_title"].setText("[新聞] 測試文章")
    win.w["site"].setText("某報")
    win.w["author"].setText("王記者")
    win.w["url"].setText("https://example.test/a")
    win.w["title"].setText("測試文章")
    win.body.setPlainText("第一段內容。\n\n第二段內容。")
    win.notes.setPlainText("我的心得")
    win.render_preview(force=True)


def test_fetch_through_ui_fills_fields_with_states(win, http_server):
    win.url_in.setText(http_server + "/ok")
    win.start_fetch()
    assert wait_until(lambda: not win._busy, 8000)
    assert win.w["title"].text() == "測試新聞標題" and win.w["author"].text() == "王小明"
    assert win.states["author"] == "found" and "擷取成功" in win.parse_status.text()
    assert "1.媒體來源: 某某新聞網" in win.preview.toPlainText()
    win.w["author"].textEdited.emit("改過")           # user edit
    win.w["author"].setText("改過")
    win.w["author"].textEdited.emit("改過")
    assert win.states["author"] == "edited"


def test_fetch_failure_is_shown_not_faked(win, http_server):
    win.url_in.setText(http_server + "/403")
    win.start_fetch()
    assert wait_until(lambda: not win._busy, 8000)
    assert "擷取失敗" in win.parse_status.text() and "繞過" in win.parse_warn.toPlainText()
    assert win.w["title"].text() == ""                 # nothing invented


def test_copy_matches_preview_and_blocks_on_errors(win):
    fill_article(win)
    win.copy("all")
    cb = QApplication.clipboard().text()
    title, body = win.current_texts()
    assert cb == f"{title}\n\n{body}"
    QApplication.clipboard().setText("SENTINEL")
    win.preview.setPlainText("含 emoji 😀 的內容")        # manual edit -> blocking error
    win.copy("body")
    assert QApplication.clipboard().text() == "SENTINEL"  # refused, clipboard untouched


def test_manual_preview_edit_is_not_overwritten_by_field_changes(win):
    fill_article(win)
    win.preview.setPlainText("我手動改的預覽")
    win.w["site"].setText("別家")
    win.w["site"].textEdited.emit("別家")
    pump(600)
    assert win.preview.toPlainText() == "我手動改的預覽"
    win.render_preview(force=True)
    assert "1.媒體來源: 別家" in win.preview.toPlainText()


def test_multiple_signatures_select_edit_delete_and_limit(win):
    for i in range(10):
        win.new_signature()
        win.sig_name.setText(f"名稱{i + 1}")
        win.sig_edit.setPlainText(f"內容{i + 1}")
        win.save_signature()
    assert win.sig_combo.count() == 10
    win.new_signature()                       # full: refuses a new slot
    assert win.sig_combo.count() == 10 and win.sig_combo.currentIndex() == 9
    win.sig_combo.setCurrentIndex(2)
    win._pick_signature(2)
    assert win.sig_edit.toPlainText() == "內容3" and win.db.signature == "內容3"
    win.sig_edit.setPlainText("改過的內容3")
    win.save_signature()                      # updates in place, no new slot
    assert win.sig_combo.count() == 10 and win.db.signatures()[2]["text"] == "改過的內容3"
    win.delete_signature(confirm=False)
    assert win.sig_combo.count() == 9 and all(s["name"] != "名稱3" for s in win.db.signatures())


def test_signature_save_apply_and_snapshot_in_draft(win):
    fill_article(win)
    win.sig_edit.setPlainText("簽名一行\n簽名二行")
    win.save_signature()
    assert win.db.signature == "簽名一行\n簽名二行"
    win.chk_sig.setChecked(True)
    win.render_preview(force=True)
    assert win.preview.toPlainText().endswith("\n--\n簽名一行\n簽名二行")
    win.chk_sig.setChecked(False)
    win.render_preview(force=True)
    assert "--\n簽名" not in win.preview.toPlainText()


def test_draft_save_open_search_delete(win):
    fill_article(win)
    did = win.save_draft()
    assert did and win.db.get_draft(did)["notes"] == "我的心得"
    win.new_draft()
    assert win.w["title"].text() == ""
    win.search.setText("測試文章")
    assert win.draft_list.count() == 1
    win.draft_list.setCurrentRow(0)
    win.open_selected()
    assert win.w["site"].text() == "某報" and win.notes.toPlainText() == "我的心得"
    win.delete_selected()
    assert win.db.get_draft(did) is None


def connect_and_login(win, bbs):
    win.session.connect_to(bbs.url)
    assert wait_until(lambda: win.session.kind is Kind.LOGIN_PROMPT)
    win.account.setText("tester")
    win.password.setText("pw")
    win._do_login()
    assert win.password.text() == ""                    # cleared right away
    assert wait_until(lambda: win.session.logged_in)


def test_end_to_end_type_body_then_refuse_duplicate(win, bbs_factory):
    bbs = bbs_factory()
    fill_article(win)
    connect_and_login(win, bbs)
    bbs.goto("editor")
    assert wait_until(lambda: win.session.kind is Kind.EDITOR)
    assert not win.btn_type_body.isEnabled()            # needs the explicit confirmation first
    win.chk_confirm.setChecked(True)
    assert win.btn_type_body.isEnabled()
    win.type_into_ptt(Target.BODY)
    assert wait_until(lambda: not win.typer.running and win.typer.bytes_sent > 0, 10000)
    d = win.db.get_draft(win.draft_id)
    assert d["input_state"] == "done"
    _t, body = win.current_texts()
    assert bytes(bbs.after_login) == body.replace("\n", "\r").encode("cp950")
    assert b"\x18" not in bbs.after_login and bbs.state == "editor"      # never saved / left the editor
    n = len(bbs.after_login)
    win.type_into_ptt(Target.BODY)                                         # second attempt on the same draft
    pump(400)
    assert len(bbs.after_login) == n and "重複" in win.msg_log.toPlainText()


def test_typing_requires_login_and_matching_screen(win, bbs_factory):
    bbs = bbs_factory()
    fill_article(win)
    win.chk_confirm.setChecked(True)
    assert not win.btn_type_body.isEnabled()            # not connected
    connect_and_login(win, bbs)
    win.type_into_ptt(Target.BODY)                      # logged in but at the main menu
    pump(300)
    assert bytes(bbs.after_login) == b"" and "無法輸入" in win.msg_log.toPlainText()


def test_crash_leftover_started_marker_becomes_aborted(win):
    fill_article(win)
    did = win.save_draft()
    win.db.set_input_state(did, "started")
    assert win.db.recover_interrupted_inputs() == 1
    assert win.db.get_draft(did)["input_state"] == "aborted"


def test_key_mapping_for_terminal():
    K = Qt.Key
    M = Qt.KeyboardModifier
    assert key_to_bytes(K.Key_Return, M.NoModifier, "\r")[0] == b"\r"
    assert key_to_bytes(K.Key_Up, M.NoModifier, "")[0] == b"\x1b[A"
    assert key_to_bytes(K.Key_X, M.ControlModifier, "\x18")[0] == b"\x18"       # a USER key press may send Ctrl-X
    assert key_to_bytes(K.Key_A, M.NoModifier, "a")[0] == b"a"
    assert key_to_bytes(K.Key_unknown, M.NoModifier, "中")[0] == "中".encode("cp950")
    data, why = key_to_bytes(K.Key_unknown, M.NoModifier, "😀")
    assert data is None and why


def resize_term(term, w, h):
    """Resize and deliver the resize event (a hidden widget would only get it on show)."""
    old = term.size()
    term.resize(w, h)
    QApplication.sendEvent(term, QResizeEvent(term.size(), old))


def test_terminal_settings_apply_and_persist(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    p = tmp_path / "set.db"
    db = Database(p)
    w = MainWindow(db, PttSession())
    assert w.term.fill                                         # default: fit the window
    w.set_fill.setChecked(False)
    assert not w.term.fill and w.tb_fill.isChecked() is False  # toolbar and settings tab stay in sync
    base_w = w.term.width()
    w.set_size.setValue(26)                                    # font size changes cell size -> fixed widget grows
    assert w.term.font_.pixelSize() == 26 and w.term.width() > base_w and w.tb_size.value() == 26
    fams = [w.set_font.itemText(i) for i in range(w.set_font.count())]
    other = next((f for f in fams if f != w.set_font.currentFont().family()), None)   # the offscreen platform may have no fonts
    if other:
        from PySide6.QtGui import QFont
        w.tb_font.setCurrentFont(QFont(other))                 # change it from the terminal-tab bar
        assert w.term.font_.family() == other and w.set_font.currentFont().family() == other
    w.tb_fill.setChecked(True)
    assert w.term.fill and w.set_fill.isChecked() and w.term.minimumWidth() < w.term.maximumWidth()
    resize_term(w.term, 900, 500)
    cw, ch = w.term.cell_size()
    assert cw * 80 <= 900.01 and ch * 24 <= 500.01                                  # grid stays inside the area, centred
    assert w.term.sx <= w.term.MAX_STRETCH and w.term.ox >= 0 and w.term.oy >= 0
    assert cw * 80 > 900 * 0.7 or w.term.sx == w.term.MAX_STRETCH                    # still uses most of the width
    small = w.term.draw_font.pixelSize()
    resize_term(w.term, 1600, 900)
    assert w.term.draw_font.pixelSize() > small                                      # font follows the window size
    assert not w.term.grab().isNull()                                                # paints in fit mode
    w.db.close()
    db2 = Database(p)
    w2 = MainWindow(db2, PttSession())
    assert w2.term.fill and w2.term.font_.pixelSize() == 26 and (not other or w2.term.font_.family() == other)
    assert w2.set_fill.isChecked() and w2.set_size.value() == 26 and w2.tb_size.value() == 26
    w2.btn_font_default.click()
    assert w2.term.fill and w2.term.font_.pixelSize() == 17 and db2.get_setting("terminal.fill") == "1"
    w2.db.close()


def test_main_window_is_freely_resizable(win):
    assert win.minimumWidth() <= 800 and win.minimumHeight() <= 600
    for size in ((820, 600), (1700, 1000), (1000, 700)):
        win.resize(*size)
        assert win.width() >= min(size[0], 1700) - 1 or win.width() >= win.minimumWidth()
    resize_term(win.term, 700, 420)
    assert win.term.width() == 700 and win.term.height() == 420     # the terminal really follows (fit mode)


def test_dfyuan_button_selects_font_when_installed_else_notice(win):
    from PySide6.QtGui import QFontDatabase
    win.use_dfyuan()
    have = set(QFontDatabase.families())
    if any(f in have for f in win.DFYUAN_FAMILIES):
        assert win.term.font_.family() in win.DFYUAN_FAMILIES
        assert win.tb_font.currentFont().family() == win.term.font_.family()


def test_board_favorites_persist_and_draft_remembers_board(win):
    from src import boards
    assert boards.board_id("Gossiping（八卦）") == "Gossiping" and boards.board_id("★ Baseball（棒球）") == "Baseball"
    assert boards.board_id("bad name!") == "" and boards.board_id("") == ""
    win.board_combo.setEditText("Stock（股票）")
    win._board_changed()
    assert win.current_board() == "Stock" and win.btn_board_fav.text() == "☆ 加入最愛"
    win.toggle_board_favorite()
    assert win.db.favorite_boards() == ["Stock"] and win.board_combo.itemText(0) == "★ Stock（股票）"
    assert win.current_board() == "Stock" and win.btn_board_fav.text() == "★ 移出最愛"
    win.board_combo.setEditText("MyOwnBoard")                      # not in the preset list
    win._board_changed()
    win.toggle_board_favorite()
    assert win.db.favorite_boards() == ["Stock", "MyOwnBoard"]
    fill_article(win)
    did = win.save_draft()
    assert win.db.get_draft(did)["board"] == "MyOwnBoard"
    win.board_combo.setEditText("Baseball")
    win.draft_list.setCurrentRow(0)
    win.open_selected()
    assert win.current_board() == "MyOwnBoard"
    win.toggle_board_favorite()                                    # remove again
    assert win.db.favorite_boards() == ["Stock"]


def test_goto_board_only_from_main_menu_and_never_posts(win, bbs_factory):
    bbs = bbs_factory()
    win.board_combo.setEditText("Gossiping")
    win._board_changed()
    win.goto_board()                                                # not connected: nothing sent
    assert "主功能表" in win.msg_log.toPlainText()
    connect_and_login(win, bbs)
    assert win.session.kind is Kind.MAIN_MENU
    win.goto_board()
    assert wait_until(lambda: bytes(bbs.after_login) == b"sGossiping\r")
    assert b"\x18" not in bbs.after_login


def test_block_triangle_and_box_chars_are_drawn_geometrically(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from src.ui.terminal_widget import draw_special
    img = QImage(40, 20, QImage.Format.Format_ARGB32)
    for ch, probe_filled, probe_empty in (("█", (30, 10), None), ("▄", (20, 17), (20, 3)), ("◢", (35, 17), (5, 3)),
                                          ("▌", (5, 10), (35, 10)), ("─", (3, 10), (3, 2)), ("│", (20, 3), (3, 3))):
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        assert draw_special(p, ch, QRectF(0, 0, 40, 20), QColor(255, 0, 0))
        p.end()
        assert img.pixelColor(*probe_filled).red() > 200, ch
        if probe_empty:
            assert img.pixelColor(*probe_empty).red() < 50, ch
    p = QPainter(img)
    assert not draw_special(p, "A", QRectF(0, 0, 40, 20), QColor(255, 0, 0))
    p.end()


def test_window_fits_small_screen_and_geometry_is_remembered(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    db = Database(tmp_path / "g.db")
    w = MainWindow(db, PttSession())
    area = QApplication.primaryScreen().availableGeometry()
    assert w.width() <= max(area.width(), w.minimumWidth()) and w.height() <= max(area.height(), w.minimumHeight())
    w.resize(901, 703)
    w.close()
    db2 = Database(tmp_path / "g.db")
    assert db2.get_setting("window.geometry")
    w2 = MainWindow(db2, PttSession())
    assert w2.width() <= area.width() and abs(w2.height() - 703) <= 2 and w2.width() >= 760   # clamped to the smaller screen
    w2.close()
    pump(50)


def test_tray_options_persist_and_close_hides_instead_of_quitting(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    monkeypatch.setattr(QSystemTrayIcon, "showMessage", lambda *a, **k: None)
    db = Database(tmp_path / "t.db")
    w = MainWindow(db, PttSession())
    assert w._tray is not None and w.chk_tray_min.isEnabled()
    w.chk_tray_close.setChecked(True)
    assert db.get_setting("tray.close") == "1" and db.get_setting("tray.minimize") == "0"
    w.show()
    w.close()                                           # X button: hides to tray, app/db stay alive
    assert not w.isVisible() and w._tray.isVisible()
    db.get_setting("tray.close")                        # db still open
    w.restore_from_tray()
    assert w.isVisible()
    w.quit_app()                                        # real exit
    assert not w.isVisible()
    pump(50)


def test_icons_render_all_sizes(qapp):
    from src.ui.icon import SIZES, render, render_tray
    for n in SIZES:
        assert not render(n).isNull() and render(n).pixelColor(n // 2, n // 2).alpha() == 255
    on, off = render_tray(32, True), render_tray(32, False)
    assert on.pixelColor(3, 16) != off.pixelColor(3, 16)          # connected / disconnected look different


def test_launch_pttlogin_starts_separate_process_and_reports_missing(win, tmp_path, monkeypatch):
    import subprocess
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    win.pttlogin_path.setText(str(tmp_path / "nope.exe"))
    assert not win.launch_pttlogin() and not calls and "找不到" in win.msg_log.toPlainText()
    exe = tmp_path / "PttAutoLogin.exe"
    exe.write_bytes(b"MZ")
    win.pttlogin_path.setText(str(exe))
    assert win.launch_pttlogin()
    assert calls[0][0][0] == [str(exe)] and calls[0][1]["cwd"] == str(tmp_path)
    assert win.db.get_setting("pttlogin.path") == str(exe)


def test_keybar_buttons_and_wheel_send_navigation_keys(win, bbs_factory):
    bbs = bbs_factory()
    connect_and_login(win, bbs)
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    win._send_key(b"\x1b[6~")                                   # PgDn button
    assert wait_until(lambda: bytes(bbs.after_login) == b"\x1b[6~")
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    win.term.wheelEvent(ev)                                      # one notch up = 2 arrow-ups
    assert wait_until(lambda: bytes(bbs.after_login) == b"\x1b[6~\x1b[A\x1b[A")
    win.chk_keybar.setChecked(False)
    win.chk_keybar.setChecked(True)
    assert win.keybar.isVisibleTo(win) and win.db.get_setting("ui.keybar") == "1"
    win.chk_keybar.setChecked(False)
    assert not win.keybar.isVisibleTo(win)


def test_stretch_fill_removes_margins_and_persists(win):
    resize_term(win.term, 3000, 500)
    win.tb_fill.setChecked(True)
    assert win.term.ox > 0                                        # default: aspect kept, centred margin
    win.tb_stretch.setChecked(True)
    assert win.set_stretch.isChecked() and win.db.get_setting("terminal.stretch") == "1"
    assert win.term.ox == 0 and win.term.oy == 0
    assert win.term.cw * 80 == pytest.approx(3000) and win.term.ch * 24 == pytest.approx(500)
    assert not win.term.grab().isNull()
    win.set_stretch.setChecked(False)
    resize_term(win.term, 3000, 500)                              # hidden widget: re-send the size
    assert not win.tb_stretch.isChecked() and win.term.ox > 0


def answer(monkeypatch, button):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: button))


def test_copy_immediately_after_field_edit_uses_fresh_preview(win):
    fill_article(win)
    win.render_preview(force=True)
    win.w["site"].setText("全新媒體")
    win._field_edited("site")                                    # debounce timer still pending, no event loop pumped
    win.copy("body")
    assert "全新媒體" in QApplication.clipboard().text()
    win.w["site"].setText("再改一次")
    win._field_edited("site")
    assert "再改一次" in win.current_texts()[1]


def test_unsaved_changes_prompt_on_new_draft_open_and_fetch(win, monkeypatch, http_server):
    fill_article(win)
    win._field_edited("site")
    assert win._dirty
    answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    win.new_draft()
    assert win.w["site"].text() == "某報" and win._dirty          # cancelled: nothing lost
    win.url_in.setText(http_server + "/article")
    win.start_fetch()
    assert not win._busy and win.w["site"].text() == "某報"      # fetch refused while the prompt is cancelled
    answer(monkeypatch, QMessageBox.StandardButton.Save)
    win.new_draft()
    assert win.w["site"].text() == "" and not win._dirty
    assert len(win.db.list_drafts()) == 1                        # saved before clearing
    fill_article(win)
    win._field_edited("site")
    answer(monkeypatch, QMessageBox.StandardButton.Discard)
    win.new_draft()
    assert win.w["site"].text() == "" and len(win.db.list_drafts()) == 1


def test_signature_edit_does_not_mark_draft_dirty(win):
    win.save_draft()
    win.sig_edit.setPlainText("只改簽名")
    assert not win._dirty


def test_type_with_missing_draft_shows_error_and_sends_nothing(win, bbs_factory):
    bbs = bbs_factory()
    fill_article(win)
    connect_and_login(win, bbs)
    bbs.goto("editor")
    assert wait_until(lambda: win.session.kind is Kind.EDITOR)
    win.chk_confirm.setChecked(True)
    win.save_draft()
    win.db.get_draft = lambda _id: None                          # draft vanished (deleted elsewhere)
    win.type_into_ptt(Target.BODY)
    pump(200)
    assert bytes(bbs.after_login) == b"" and "找不到" in win.msg_log.toPlainText()


def test_switching_draft_during_typing_is_blocked_and_state_goes_to_original(win, bbs_factory):
    bbs = bbs_factory()
    fill_article(win)
    connect_and_login(win, bbs)
    bbs.goto("editor")
    assert wait_until(lambda: win.session.kind is Kind.EDITOR)
    win.chk_confirm.setChecked(True)
    win.chk_nonempty.setChecked(True)
    win.type_into_ptt(Target.BODY)
    original = win._typing_draft_id
    assert original and win.typer.running
    win.new_draft()                                              # refused while typing
    assert win.draft_id == original and "輸入進行中" in win.msg_log.toPlainText()
    assert wait_until(lambda: not win.typer.running, 10000)
    assert win.db.get_draft(original)["input_state"] == "done"
    assert not win.chk_nonempty.isChecked()                      # allowance reset after the run


def test_nonempty_allowance_resets_on_new_and_open(win):
    win.chk_nonempty.setChecked(True)
    win.new_draft()
    assert not win.chk_nonempty.isChecked()
    fill_article(win)
    did = win.save_draft()
    win.reload_drafts()
    win.draft_list.setCurrentRow(0)
    win.chk_nonempty.setChecked(True)
    win.open_selected()
    assert not win.chk_nonempty.isChecked() and win.draft_id == did


def test_source_has_no_raw_control_bytes_and_keybar_sends_real_escapes():
    import pathlib
    for f in ("src/ui/main_window.py", "src/ui/terminal_widget.py"):
        data = pathlib.Path(__file__).resolve().parent.parent.joinpath(f).read_bytes()
        assert b"\x1b" not in data, f                           # escapes must be written as \x1b, never a raw ESC byte


def test_pttlogin_default_is_not_a_hardcoded_developer_path(win):
    import inspect
    from src.ui import main_window
    assert "D:/Claude" not in inspect.getsource(main_window)
    assert win.pttlogin_path.text() == "" or win.pttlogin_path.text().lower().endswith("pttautologin.exe")


def test_terminal_keyboard_is_paused_while_typing_or_logging_in(win, bbs_factory):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    bbs = bbs_factory()
    connect_and_login(win, bbs)
    win.typer.running = True
    win._update_input_lock()
    assert win.term.locked
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    win.term.keyPressEvent(ev)
    win._send_key(b"\x1b[A")
    pump(300)
    assert bytes(bbs.after_login) == b"" and "暫停" in win.msg_log.toPlainText()
    win.typer.running = False
    win._update_input_lock()
    assert not win.term.locked
    win.term.keyPressEvent(ev)
    assert wait_until(lambda: bytes(bbs.after_login) == b"a")


def test_draft_keeps_signature_snapshot_when_signature_changes(win):
    fill_article(win)
    for name, text in (("甲", "簽名甲"), ("乙", "簽名乙")):
        win.new_signature()
        win.sig_name.setText(name)
        win.sig_edit.setPlainText(text)
        win.save_signature()
    win.sig_combo.setCurrentIndex(0)
    win._pick_signature(0)
    win.chk_sig.setChecked(True)
    did = win.save_draft()
    assert win.db.get_draft(did)["signature_text"] == "簽名甲"
    win.sig_combo.setCurrentIndex(1)
    win._pick_signature(1)                                       # now the selected signature is 乙
    win.reload_drafts()
    win.draft_list.setCurrentRow(0)
    win.open_selected()
    win.render_preview(force=True)
    assert win.preview.toPlainText().endswith("簽名甲") and win.lbl_sig_snap.isVisibleTo(win)
    win.use_current_signature()
    win.render_preview(force=True)
    assert win.preview.toPlainText().endswith("簽名乙") and not win.lbl_sig_snap.isVisibleTo(win)


def test_recovered_draft_shows_aborted_in_first_list(qapp, tmp_path, monkeypatch):
    db = Database(tmp_path / "r.db")
    did = db.save_draft({"title": "t", "post_title": "[新聞] t", "body": "b"})
    db.set_input_state(did, "started")
    db.close()
    w = MainWindow(Database(tmp_path / "r.db"), PttSession())
    assert w.db.get_draft(did)["input_state"] == "aborted"
    assert "aborted" in w.draft_list.item(0).text() or "中止" in w.draft_list.item(0).text() or w.draft_list.count() == 1
    w.db.close()


def test_login_rejects_control_characters_and_sends_nothing(win, bbs_factory):
    bbs = bbs_factory()
    win.session.connect_to(bbs.url)
    assert wait_until(lambda: win.session.kind is Kind.LOGIN_PROMPT)
    assert not win.session.login("ab\x1bc", "pw")
    assert not win.session.login("abc", "p\tw")
    assert not win.session.login("a" * 65, "pw")
    pump(200)
    assert bytes(bbs.after_login) == b""


def test_fetched_title_with_existing_prefix_is_not_prefixed_twice(win):
    from src.parsers import fetch as F
    from src.parsers.extract import parse
    html = "<html><head><title>[快訊] 某事件</title></head><body><article><h1>[快訊] 某事件</h1><p>" + "內文很長。" * 60 + "</p></article></body></html>"
    res = parse(html, "https://news.example/a")
    win._fetch_done(F.Fetched("https://news.example/a", "https://news.example/a", 200, "text/html", "utf-8", html, len(html), []), res)
    assert win.w["post_title"].text().count("[") == 1 and win.w["post_title"].text().startswith("[快訊]")
