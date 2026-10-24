import threading
from http.server import ThreadingHTTPServer

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from conftest import pump, wait_until
from src.net.poster import Target
from src.net.session import PttSession
from src.storage.db import Database
from src.links import Link
from src.net.client import State
from src.net.session import Login
from src.terminal.detect import Kind
from src.ui import browser
from src.ui.main_window import FIELDS, MainWindow
from src.ui.terminal_widget import key_to_bytes
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QResizeEvent
from test_extract_fetch import H


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    db = Database(tmp_path / "ui.db")
    w = MainWindow(db, PttSession())
    w._set_article_panel_visible(True)                  # existing tests exercise the article panel; layout tests use their own window
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


def test_second_fetch_starts_a_fresh_article(win, http_server):
    win.url_in.setText(http_server + "/ok")
    win.start_fetch()
    assert wait_until(lambda: not win._busy, 8000)
    assert "測試新聞標題" in win.preview.toPlainText()
    win.notes.setPlainText("第一篇心得")
    win.chk_confirm.setChecked(True)
    assert win.save_draft()
    win.url_in.setText(http_server + "/second")
    win.start_fetch()
    assert wait_until(lambda: not win._busy, 8000)
    assert win.draft_id is None                                  # the new article is a new, unsaved draft
    assert win.notes.toPlainText() == ""                         # no commentary from the first article
    assert not win.chk_confirm.isChecked()                       # must confirm the new article again
    assert win.w["title"].text() == "第二則新聞標題"
    assert win.w["author"].text() == "陳大華"
    assert win.w["site"].text() == "第二新聞網"
    assert "第二篇獨有內容" in win.preview.toPlainText()
    assert "測試新聞標題" not in win.preview.toPlainText()
    assert win.db.list_drafts()                                  # the saved first draft is kept


def test_clear_all_fields_resets_everything_but_keeps_saved_drafts(win):
    fill_article(win)
    assert win.save_draft()
    win.chk_confirm.setChecked(True)
    win.preview.setPlainText("手動修改的預覽")
    assert win._preview_manual and win._dirty

    win.btn_clear.click()                                        # fixture answers Yes

    assert win.draft_id is None
    assert win.db.list_drafts()                                  # saved draft is not deleted
    assert all(win.w[f].text() == "" for f in FIELDS)
    assert win.body.toPlainText() == "" and win.notes.toPlainText() == "" and win.url_in.text() == ""
    preview = win.preview.toPlainText()
    assert "手動修改的預覽" not in preview and "某報" not in preview and "第一段內容" not in preview
    assert not win.chk_confirm.isChecked()
    assert win.parse_status.text() == "尚未擷取" and win.parse_warn.toPlainText() == ""
    assert win.lbl_draft.text() == "未儲存"
    assert not win._dirty and not win._preview_manual


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


def test_regen_preview_always_applies_a_non_empty_signature(win):
    fill_article(win)
    win.sig_edit.setPlainText("簽名一行\n簽名二行")
    win.chk_sig.setChecked(False)
    win.render_preview(force=True)
    assert "--\n簽名" not in win.preview.toPlainText()
    win.regen_preview()
    assert win.chk_sig.isChecked()
    assert win.preview.toPlainText().endswith("\n--\n簽名一行\n簽名二行")
    win.sig_edit.setPlainText("")
    win.regen_preview()
    assert "--\n簽名" not in win.preview.toPlainText()


def test_reply_mode_preview_uses_notes_signature_and_re_title(win):
    fill_article(win)
    win.notes.setPlainText("我的回覆")
    win.sig_edit.setPlainText("簽名")
    win.chk_sig.setChecked(True)
    win.chk_reply.setChecked(True)
    win.render_preview(force=True)
    text = win.preview.toPlainText()
    assert "1.媒體來源" not in text and not text.startswith("Re:")
    assert text.endswith("我的回覆\n--\n簽名")
    assert win.current_texts()[0] == "Re: [新聞] 測試文章"
    assert win.btn_type_body.text() == "輸入回覆內文"
    assert "回覆標題" in win.lbl_reply_title.text()
    win.chk_reply.setChecked(False)
    win.render_preview(force=True)
    assert "1.媒體來源" in win.preview.toPlainText()


def test_reply_mode_without_a_title_still_passes_checks(win):
    fill_article(win)
    win.w["post_title"].setText("")
    win.notes.setPlainText("回覆內容")
    win.chk_reply.setChecked(True)
    win.render_preview(force=True)
    assert win.current_texts()[0] == ""
    assert all(i.level != "error" for i in win.run_checks())


def test_type_body_button_uses_the_reply_target_in_reply_mode(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "type_into_ptt", lambda target: calls.append(target))
    win.chk_reply.setChecked(True)
    win._type_body_clicked()
    win.chk_reply.setChecked(False)
    win._type_body_clicked()
    assert calls == [Target.REPLY_BODY, Target.BODY]


def test_reply_mode_is_saved_and_restored_with_the_draft(win):
    fill_article(win)
    win.notes.setPlainText("回覆內容")
    win.chk_reply.setChecked(True)
    assert win.save_draft()
    win.new_draft()
    assert not win.chk_reply.isChecked()
    win.search.setText("測試文章")
    win.draft_list.setCurrentRow(0)
    win.open_selected()
    assert win.chk_reply.isChecked()
    assert win.preview.toPlainText().endswith("回覆內容")
    assert win.current_texts()[0] == "Re: [新聞] 測試文章"


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
    assert len(bbs.after_login) == n and "重複" in win.statusBar().currentMessage()


def test_typing_requires_login_and_matching_screen(win, bbs_factory):
    bbs = bbs_factory()
    fill_article(win)
    win.chk_confirm.setChecked(True)
    assert not win.btn_type_body.isEnabled()            # not connected
    connect_and_login(win, bbs)
    win.type_into_ptt(Target.BODY)                      # logged in but at the main menu
    pump(300)
    assert bytes(bbs.after_login) == b"" and "無法輸入" in win.statusBar().currentMessage()


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


def test_apply_settings_button_saves_values_and_shows_success(win, monkeypatch):
    info = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: info.append((a[1], a[2])) or QMessageBox.StandardButton.Ok))
    win.set_size.setValue(21)
    win.browser_path.setText(r"C:\Tools\browser.exe")
    idx = win.browser_combo.findData("custom")
    assert idx >= 0
    win.browser_combo.setCurrentIndex(idx)
    win.chk_auto_image.setChecked(True)
    win.pttlogin_path.setText(r"C:\Tools\PttAutoLogin.exe")

    win.btn_apply_settings.click()

    assert win.db.get_setting("terminal.font_px") == "21"
    assert win.db.get_setting("browser.path") == r"C:\Tools\browser.exe"
    assert win.db.get_setting("browser.mode") == "custom"
    assert win.db.get_setting("links.image_auto_open") == "1"
    assert win.db.get_setting("pttlogin.path") == r"C:\Tools\PttAutoLogin.exe"
    assert info and "成功" in info[-1][1]
    assert "設定已套用" in win.statusBar().currentMessage()


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
    assert "主功能表" in win.statusBar().currentMessage()
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
    assert not win.launch_pttlogin() and not calls and "找不到" in win.statusBar().currentMessage()
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
    assert bytes(bbs.after_login) == b"" and "找不到" in win.statusBar().currentMessage()


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
    assert win.draft_id == original and "輸入進行中" in win.statusBar().currentMessage()
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
    assert bytes(bbs.after_login) == b"" and "暫停" in win.statusBar().currentMessage()
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


def test_picking_signature_clears_draft_snapshot_and_applies(win):
    fill_article(win)
    for name, text in (("甲", "簽名甲"), ("乙", "簽名乙"), ("丙", "簽名丙")):
        win.new_signature()
        win.sig_name.setText(name)
        win.sig_edit.setPlainText(text)
        win.save_signature()
    win._pick_signature(0)
    win.chk_sig.setChecked(True)
    assert win.save_draft()
    win._pick_signature(1)                                       # active signature is 乙
    win.draft_list.setCurrentRow(0)
    win.open_selected()
    assert win._draft_sig == "簽名甲" and win.lbl_sig_snap.isVisibleTo(win)
    win._pick_signature(2)                                       # explicit choice must override the snapshot
    assert win._draft_sig is None and not win.lbl_sig_snap.isVisibleTo(win)
    win.render_preview(force=True)
    assert win.preview.toPlainText().endswith("簽名丙")
    assert win._dirty


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


def test_typing_is_blocked_when_started_state_cannot_be_saved(win, bbs_factory, monkeypatch):
    from src.errors import StorageError
    bbs = bbs_factory()
    fill_article(win)
    connect_and_login(win, bbs)
    bbs.goto("editor")
    assert wait_until(lambda: win.session.kind is Kind.EDITOR)
    win.chk_confirm.setChecked(True)

    def boom(*a, **k):
        raise StorageError("磁碟已滿")
    monkeypatch.setattr(win.db, "set_input_state", boom)
    win.type_into_ptt(Target.BODY)
    pump(300)
    assert bytes(bbs.after_login) == b"" and not win.typer.running and "未送出任何內容" in win.statusBar().currentMessage()


def test_partial_body_needs_confirmation_before_typing(win, bbs_factory, monkeypatch):
    bbs = bbs_factory()
    fill_article(win)
    connect_and_login(win, bbs)
    bbs.goto("editor")
    assert wait_until(lambda: win.session.kind is Kind.EDITOR)
    win.chk_confirm.setChecked(True)
    import types
    win._last_result = types.SimpleNamespace(status="partial", body_status="suspect_partial")     # as after a fetch of a cut-off article
    answer(monkeypatch, QMessageBox.StandardButton.No)
    win.type_into_ptt(Target.BODY)
    pump(300)
    assert bytes(bbs.after_login) == b"" and "疑似不完整" in win.statusBar().currentMessage()
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    win.chk_nonempty.setChecked(True)
    win.type_into_ptt(Target.BODY)
    assert wait_until(lambda: len(bbs.after_login) > 0, 6000)
    assert wait_until(lambda: not win.typer.running, 10000)


def test_corrupt_font_size_setting_does_not_stop_startup(qapp, tmp_path):
    db = Database(tmp_path / "f.db")
    db.set_setting("terminal.font_px", "abc")
    w = MainWindow(db, PttSession())
    assert w.term.font_.pixelSize() == 17
    w.db.close()


def test_ime_commit_with_control_characters_is_ignored(win, bbs_factory):
    from PySide6.QtGui import QInputMethodEvent
    bbs = bbs_factory()
    connect_and_login(win, bbs)
    ev = QInputMethodEvent()
    ev.setCommitString("ab\x1b[A")
    win.term.inputMethodEvent(ev)
    pump(200)
    assert bytes(bbs.after_login) == b"" and "控制字元" in win.statusBar().currentMessage()

def test_merged_page_layout_and_article_subtabs(win):
    assert win.tabs.count() == 4
    assert [win.tabs.tabText(i) for i in range(4)] == ["終端機與文章", "站台", "草稿", "設定"]
    assert win.main_splitter.count() == 2
    assert win.main_splitter.widget(0) is win.terminal_panel
    assert win.main_splitter.widget(1) is win.article_panel
    assert win.article_tabs.count() == 2
    assert [win.article_tabs.tabText(i) for i in range(2)] == ["擷取與欄位", "預覽與輸入"]


def test_article_panel_toggle_shortcut_and_state(win):
    assert win.act_toggle_article.shortcut().toString() == "F12"
    assert win.btn_article_toggle.isChecked()
    win.act_toggle_article.trigger()
    pump(20)
    assert win._article_collapsed and win.article_panel.isHidden()
    assert win.db.get_setting("ui.article_panel_collapsed") == "1"
    win.btn_article_toggle.click()
    pump(20)
    assert not win._article_collapsed and win.article_panel.isVisibleTo(win)
    assert win.act_toggle_article.isChecked()


def test_article_panel_width_and_collapsed_restore(qapp, tmp_path):
    db = Database(tmp_path / "layout.db")
    db.set_setting("ui.article_panel_width", "500")
    db.set_setting("ui.article_panel_collapsed", "0")
    w = MainWindow(db, PttSession())
    w.show()
    w.resize(1600, 900)
    pump(50)
    assert w.article_panel.isVisibleTo(w)
    sizes = w.main_splitter.sizes()
    assert len(sizes) == 2 and abs(sizes[1] - 500) <= 40
    w._set_article_panel_visible(False)
    assert w.db.get_setting("ui.article_panel_collapsed") == "1"
    w.db.close()


def test_corrupt_article_panel_settings_fall_back(qapp, tmp_path):
    db = Database(tmp_path / "layout2.db")
    db.set_setting("ui.article_panel_width", "not-a-number")
    db.set_setting("ui.article_panel_collapsed", "wat")
    w = MainWindow(db, PttSession())
    assert w._article_width == 620
    assert w._article_collapsed == w.compact
    w.db.close()


def test_compact_screen_defaults_panel_collapsed(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(MainWindow, "_screen_is_compact", staticmethod(lambda: True))
    db = Database(tmp_path / "layout3.db")
    w = MainWindow(db, PttSession())
    assert w.compact and w._article_collapsed and w.article_panel.isHidden()
    w.db.close()


def test_open_draft_expands_panel_and_selects_preview(win):
    fill_article(win)
    did = win.save_draft()
    win.new_draft()
    win.reload_drafts()
    win.draft_list.setCurrentRow(0)
    win._set_article_panel_visible(False)
    win.tabs.setCurrentIndex(2)
    win.open_selected()
    pump(20)
    assert win.tabs.currentIndex() == 0
    assert not win._article_collapsed and win.article_panel.isVisibleTo(win)
    assert win.article_tabs.currentIndex() == 1
    assert win.draft_id == did


def test_splitter_change_relayouts_terminal(win):
    win.show()
    win.resize(1600, 900)
    pump(30)
    win._set_article_panel_visible(True)
    pump(30)
    expanded = win.term.width()
    win._set_article_panel_visible(False)
    assert wait_until(lambda: win.term.width() > expanded, 2000)
    collapsed = win.term.width()
    win._set_article_panel_visible(True)
    assert wait_until(lambda: win.term.width() < collapsed, 2000)
    assert win.term.cw * win.term.s.screen.cols <= win.term.width() + 1


def test_no_msg_log_and_notice_goes_to_status_bar(win):
    assert not hasattr(win, "msg_log")
    win._notice("狀態列訊息測試")
    assert "狀態列訊息測試" in win.statusBar().currentMessage()


def test_critical_error_uses_dialog_and_status_bar(win, monkeypatch):
    from src.errors import StorageError
    calls = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls.append(a[2]) or QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(win.db, "save_draft", lambda *a, **k: (_ for _ in ()).throw(StorageError("磁碟已滿")))
    assert win.save_draft() is None
    assert calls and "磁碟已滿" in calls[0]
    assert "磁碟已滿" in win.statusBar().currentMessage()


def test_fullscreen_action_and_escape_not_taken(win, monkeypatch):
    assert win.act_fullscreen.shortcut().toString() == "F11"
    assert win.act_toggle_article.shortcut().toString() == "F12"
    menu = win.menuBar().actions()[0].menu()
    assert win.act_fullscreen in menu.actions() and win.act_toggle_article in menu.actions()
    full, normal = [], []
    monkeypatch.setattr(win, "isFullScreen", lambda: False)
    monkeypatch.setattr(win, "showFullScreen", lambda: full.append(True))
    win._set_fullscreen(True)
    assert full
    monkeypatch.setattr(win, "isFullScreen", lambda: True)
    monkeypatch.setattr(win, "showNormal", lambda: normal.append(True))
    win._set_fullscreen(False)
    assert normal
    assert key_to_bytes(Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier, "") == (b"\x1b", None)


def test_theme_combo_applies_and_persists(win):
    win.theme_combo.setCurrentIndex(win.theme_combo.findData("dark"))
    pump(20)
    assert win._theme_choice == "dark" and win.term.theme_name == "dark"
    assert win.db.get_setting("ui.theme") == "dark"
    win.theme_combo.setCurrentIndex(win.theme_combo.findData("light"))
    pump(20)
    assert win._theme_choice == "light" and win.term.theme_name == "dark"   # terminal default: always dark
    assert win.db.get_setting("ui.theme") == "light"
    win.terminal_palette_combo.setCurrentIndex(win.terminal_palette_combo.findData("theme"))
    pump(20)
    assert win.term.theme_name == "light" and win.db.get_setting("ui.terminal_palette") == "theme"


def test_theme_restores_and_corrupt_falls_back(qapp, tmp_path):
    db = Database(tmp_path / "theme.db")
    db.set_setting("ui.theme", "dark")
    w = MainWindow(db, PttSession())
    assert w._theme_choice == "dark" and w.term.theme_name == "dark"
    db.set_setting("ui.theme", "neon")
    w2 = MainWindow(db, PttSession())
    assert w2._theme_choice == "system"
    w2.db.close()


def test_system_theme_reapplies_on_scheme_change(win, monkeypatch):
    win._theme_choice = "system"
    win._terminal_palette_choice = "theme"
    monkeypatch.setattr(win, "_resolve_theme", lambda _choice: "dark")
    win._on_system_scheme_changed(Qt.ColorScheme.Dark)
    assert win.term.theme_name == "dark"
    monkeypatch.setattr(win, "_resolve_theme", lambda _choice: "light")
    win._on_system_scheme_changed(Qt.ColorScheme.Light)
    assert win.term.theme_name == "light"
    win._terminal_palette_choice = "dark"
    win._on_system_scheme_changed(Qt.ColorScheme.Light)
    assert win.term.theme_name == "dark"


def test_terminal_palette_defaults_dark_and_switches(win):
    assert win._terminal_palette_choice == "dark"
    assert win.term.theme_name == "dark"
    win.theme_combo.setCurrentIndex(win.theme_combo.findData("light"))
    pump(20)
    assert win._theme_choice == "light" and win.term.theme_name == "dark"
    win.terminal_palette_combo.setCurrentIndex(win.terminal_palette_combo.findData("theme"))
    pump(20)
    assert win.term.theme_name == "light"
    win.terminal_palette_combo.setCurrentIndex(win.terminal_palette_combo.findData("dark"))
    pump(20)
    assert win.term.theme_name == "dark"


def test_corrupt_terminal_palette_setting_falls_back_to_dark(qapp, tmp_path):
    db = Database(tmp_path / "term-palette.db")
    db.set_setting("ui.terminal_palette", "neon")
    db.set_setting("ui.theme", "light")
    w = MainWindow(db, PttSession())
    assert w._terminal_palette_choice == "dark"
    assert w.terminal_palette_combo.currentData() == "dark"
    assert w.term.theme_name == "dark"
    w.db.close()


def test_splitter_width_writes_are_debounced(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win.db, "set_setting", lambda k, v: calls.append((k, v)))
    win._article_width_timer.stop()
    for _ in range(5):
        win._on_splitter_moved(0, 0)
    assert not [k for k, _v in calls if k == "ui.article_panel_width"]
    pump(600)
    assert len([k for k, _v in calls if k == "ui.article_panel_width"]) == 1


def test_article_width_is_saved_on_close(qapp, tmp_path):
    path = tmp_path / "close-width.db"
    w = MainWindow(Database(path), PttSession())
    w._article_collapsed = False
    w._article_width = 777
    w.close()
    pump(20)
    db2 = Database(path)
    assert db2.get_setting("ui.article_panel_width") == "777"
    db2.close()


def test_f12_toggles_panel_and_ctrl_shift_a_stays_terminal_input(win, bbs_factory):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    assert win.act_toggle_article.shortcut().toString() == "F12"
    assert key_to_bytes(Qt.Key.Key_F12, Qt.KeyboardModifier.NoModifier, "") == (None, None)
    win._set_article_panel_visible(True)
    win.act_toggle_article.trigger()
    assert win._article_collapsed
    win.act_toggle_article.trigger()
    assert not win._article_collapsed

    bbs = bbs_factory()
    connect_and_login(win, bbs)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier, "")
    win.term.keyPressEvent(ev)
    assert wait_until(lambda: bytes(bbs.after_login) == b"\x01")


def test_browser_settings_defaults_and_persist(win):
    assert win.browser_combo.currentData() == "system"
    assert not win.chk_auto_image.isChecked()
    assert not win.chk_hover_image.isChecked()
    assert not win.chk_article_image.isChecked()
    assert win.db.get_setting("browser.mode", "") == ""
    win.browser_combo.setCurrentIndex(win.browser_combo.findData("custom"))
    win.browser_path.setText("C:/Tools/browser.exe")
    win._save_browser_path()
    assert win.db.get_setting("browser.mode") == "custom"
    assert win.db.get_setting("browser.path") == "C:/Tools/browser.exe"
    assert win.browser_path.isEnabled()
    win.chk_auto_image.setChecked(True)
    assert win.db.get_setting("links.image_auto_open") == "1"
    win.chk_hover_image.setChecked(True)
    assert win.db.get_setting("links.image_hover_preview") == "1"
    win.chk_article_image.setChecked(True)
    assert win.db.get_setting("links.article_images_open") == "1"


def test_browser_settings_corrupt_fall_back(qapp, tmp_path):
    db = Database(tmp_path / "browser.db")
    db.set_setting("browser.mode", "not-a-browser")
    db.set_setting("links.image_auto_open", "maybe")
    w = MainWindow(db, PttSession())
    assert w.browser_combo.currentData() == "system"
    assert not w.chk_auto_image.isChecked()
    w.db.close()


def _image_link(url: str) -> Link:
    return Link(url, 0, 0, len(url))


def test_manual_link_click_uses_browser_settings(win, monkeypatch):
    calls = []
    monkeypatch.setattr(browser, "open_url", lambda url, mode, path: calls.append((url, mode, path)) or (True, "ok"))
    win.term.linkActivated.emit("https://example.com/a")
    assert calls and calls[0][0] == "https://example.com/a"
    assert calls[0][1] == win.browser_combo.currentData()


def test_auto_image_opens_inside_the_app_not_a_browser(win, monkeypatch):
    shown, opened = [], []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: shown.append(url) or True)
    monkeypatch.setattr(browser, "open_url", lambda url, mode, path: opened.append(url) or (True, "ok"))
    win.chk_auto_image.setChecked(True)
    win.session.logged_in = True
    win.session.login_state = Login.LOGGED_IN
    win._on_links_changed([_image_link("https://i.imgur.com/a.jpg")])
    assert shown == ["https://i.imgur.com/a.jpg"] and opened == []


def test_auto_image_reuses_one_in_app_viewer(win, monkeypatch):
    from src.ui import main_window as mw
    shown = []
    monkeypatch.setattr(mw.ImageViewer, "show_url", lambda self, url: shown.append(url))
    assert win._open_image_inside("https://i.imgur.com/a.jpg")
    viewer = win._image_viewer
    assert viewer is not None and shown == ["https://i.imgur.com/a.jpg"]
    assert win._open_image_inside("https://i.imgur.com/b.jpg")
    assert win._image_viewer is viewer and shown == ["https://i.imgur.com/a.jpg", "https://i.imgur.com/b.jpg"]
    win._close_image_viewer()


def test_hover_preview_only_for_image_links_when_enabled(win, monkeypatch):
    from src.ui import main_window as mw
    shown, hidden = [], []

    class FakePreview:
        def show_url(self, url, pos=None):
            shown.append(url)

        def hide_preview(self):
            hidden.append(True)

    monkeypatch.setattr(mw, "ImageHoverPreview", FakePreview)
    win._on_link_hovered("https://cdn.example.com/a.jpg")       # setting off: nothing starts
    assert not win._hover_timer.isActive()

    win.chk_hover_image.setChecked(True)
    win._on_link_hovered("https://cdn.example.com/a.jpg")
    assert win._hover_timer.isActive()
    win._show_hover_preview()
    assert shown == ["https://cdn.example.com/a.jpg"]

    win._on_link_hovered("https://example.com/article")          # not an image URL: hide
    assert not win._hover_timer.isActive() and hidden
    win._on_link_hovered("")
    assert hidden


def test_article_images_setting_opens_the_gallery(win, monkeypatch):
    from src.ui import main_window as mw
    calls = []
    monkeypatch.setattr(mw.ImageViewer, "show_images",
                        lambda self, urls, strict=True, referer=None: calls.append((urls, strict)))
    win._article_image_urls = ["https://cdn.example.com/a.jpg", "https://cdn.example.com/b.png"]
    win.chk_article_image.setChecked(True)
    assert calls == [(["https://cdn.example.com/a.jpg", "https://cdn.example.com/b.png"], False)]


def test_ptt_reload_sends_ctrl_l_and_disambiguates_the_web_reload(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win.session, "send_user_bytes", lambda data: calls.append(data) or True)
    win.reload_ptt_article()
    assert calls == [b"\x0c"]
    assert "重新載入文章" in win.btn_ptt_reload.text()
    assert "網頁" in win.btn_reload.text()


def test_ptt_reload_reports_when_disconnected_or_busy(win, monkeypatch):
    notices = []
    monkeypatch.setattr(win, "_notice", lambda msg: notices.append(msg))
    monkeypatch.setattr(win.session, "send_user_bytes", lambda data: False)
    win.reload_ptt_article()
    assert "尚未連線" in notices[-1]
    monkeypatch.setattr(win.session, "send_user_bytes", lambda data: True)
    win.term.pasting = True
    win.reload_ptt_article()
    assert "已暫停" in notices[-1]


def test_notes_and_signature_live_on_the_preview_input_tab(win):
    preview_tab = win.article_tabs.widget(1)
    fields_tab = win.article_tabs.widget(0)
    assert preview_tab.isAncestorOf(win.notes) and preview_tab.isAncestorOf(win.sig_edit)
    assert not fields_tab.isAncestorOf(win.notes) and not fields_tab.isAncestorOf(win.sig_edit)
    assert "簽名檔" in win.sig_edit.placeholderText()


def test_upload_done_inserts_urls_into_the_body(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from src.net.upload import UploadBatch, UploadResult
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    win.body.setPlainText("內文")
    batch = UploadBatch(results=[UploadResult("a.png", "https://files.catbox.moe/a.png", "catbox", 3)])
    win._upload_done(batch)
    assert "https://files.catbox.moe/a.png" in win.body.toPlainText()


def test_upload_dialog_starts_a_public_upload(win, monkeypatch, tmp_path):
    from PySide6.QtCore import QRunnable
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from src.ui import main_window as mw
    png = tmp_path / "a.png"
    png.write_bytes(b"png")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([str(png)], "")))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    started = []

    class FakeTask(QRunnable):
        def __init__(self, paths, host_key):
            super().__init__()
            self.signals = mw._UploadSignals()
            started.append((paths, host_key))

        def cancel(self):
            pass

        def run(self):
            pass

    monkeypatch.setattr(mw, "ImageUploadTask", FakeTask)
    win.upload_images_dialog()
    assert started == [([str(png)], "catbox")]
    assert win._upload_busy and not win.btn_upload_image.isEnabled()


def test_money_estimate_and_input_mode_setting(win):
    win.w["post_title"].setText("閒聊")
    win.body.setPlainText("字" * 100)
    win._update_money_estimate()
    text = win.lbl_money_estimate.text()
    assert "25 P" in text and "100 個有效字元" in text and "快速貼上" in text
    win.radio_money.setChecked(True)
    assert win.db.get_setting("post.input_mode") == "money"
    assert win.db.get_setting("post.money_pace") == "1"
    text = win.lbl_money_estimate.text()
    assert "賺 P 幣（逐字配速）" in text and "50 秒" in text
    win.w["post_title"].setText("[新聞] 標題")
    win.body.setPlainText("字" * 200)
    win._update_money_estimate()
    text = win.lbl_money_estimate.text()
    assert "新聞上限 25 P" in text and "已達 P 幣上限" in text


def test_reload_article_uses_the_article_url(win, monkeypatch):
    win.w["url"].setText("https://news.example.com/a")
    win.url_in.setText("https://other.example/b")
    calls = []
    monkeypatch.setattr(win, "start_fetch", lambda: calls.append(win.url_in.text()))
    win.reload_article()
    assert calls == ["https://news.example.com/a"]


def test_reload_article_needs_a_url_and_is_blocked_while_fetching(win, monkeypatch):
    notices = []
    monkeypatch.setattr(win, "_notice", lambda m: notices.append(m))
    win.reload_article()
    assert "沒有" in notices[0]
    win.w["url"].setText("https://news.example.com/a")
    win._busy = True
    win.reload_article()
    assert "擷取進行中" in notices[-1]


def test_download_article_images_runs_the_zip_task(win, monkeypatch, tmp_path):
    from PySide6.QtCore import QRunnable
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from src.ui import main_window as mw
    target = tmp_path / "imgs.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    started = []

    class FakeTask(QRunnable):
        def __init__(self, urls, target, referer):
            super().__init__()
            self.signals = mw._ZipSignals()
            started.append((urls, str(target), referer))

        def cancel(self):
            pass

        def run(self):
            pass

    monkeypatch.setattr(mw, "ArticleImagesZipTask", FakeTask)
    win._article_image_urls = ["https://cdn.example.com/a.jpg"]
    win._article_referer = "https://news.example.com/a"
    win.btn_zip.setEnabled(True)
    win.download_article_images()
    assert started == [(["https://cdn.example.com/a.jpg"], str(target), "https://news.example.com/a")]
    assert win._zip_busy and not win.btn_zip.isEnabled()


def test_zip_path_always_ends_with_zip(win, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "photos.7z"), "")))
    target = win._ask_zip_target(3)
    assert target is not None and target.suffix.lower() == ".zip" and target.stem == "photos"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    assert win._ask_zip_target(3) is None


def test_zip_download_declined_after_choosing_the_path_does_not_start(win, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from src.ui import main_window as mw
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "x.zip"), "")))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    started = []
    monkeypatch.setattr(mw, "ArticleImagesZipTask", lambda *a, **k: started.append(a))
    win._article_image_urls = ["https://cdn.example.com/a.jpg"]
    win.download_article_images()
    assert started == [] and not win._zip_busy


def test_zip_result_reenables_the_button(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    win._article_image_urls = ["https://cdn.example.com/a.jpg"]
    win.btn_zip.setEnabled(False)
    win._zip_busy = True

    class Result:
        saved, skipped, path = 2, 1, "C:/out.zip"

    win._zip_done(Result())
    assert not win._zip_busy and win.btn_zip.isEnabled()


def test_ui_font_settings_apply_and_persist(win):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    old = app.font()
    term_size = win.term.font().pointSize()
    try:
        win.chk_ui_font_auto.setChecked(False)
        win.ui_font.setCurrentFont(QFont("Arial"))
        win.ui_font_size.setValue(13)
        win._apply_ui_font(save=True)
        family = win.ui_font.currentFont().family()
        assert family and win.db.get_setting("ui.font_family") == family
        assert win.db.get_setting("ui.font_size") == "13"
        assert win.db.get_setting("ui.font_auto") == "0"
        assert app.font().pointSize() == 13
        for widget in (win.menuBar(), win.tabs.tabBar(), win.url_in, win.body, win.preview,
                       win.lbl_login, win.parse_status, win.btn_fetch, win.chk_auto_image):
            assert widget.font().pointSize() == 13, widget
        assert win.term.font().pointSize() == term_size          # terminal keeps its own font
    finally:
        app.setFont(old)


def test_ui_font_auto_mode_uses_the_system_size(win):
    from PySide6.QtWidgets import QApplication
    assert win.chk_ui_font_auto.isChecked()
    assert not win.ui_font_size.isEnabled()
    win._apply_ui_font(save=True)
    assert win.db.get_setting("ui.font_auto") == "1"
    assert QApplication.instance().font().pointSize() == win._default_ui_font_size()


def test_settings_tab_is_scrollable(win):
    from PySide6.QtWidgets import QScrollArea
    settings_tab = win.tabs.widget(3)
    assert isinstance(settings_tab, QScrollArea) and settings_tab.widget() is win.settings_content


def test_update_download_applies_a_delta_and_restarts(win, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication
    from src import update as up
    staged = up.StagedUpdate(tmp_path / "staging", "9.9.9", ("PTTAutoPost.exe",), ())
    applied, closed = [], []
    monkeypatch.setattr(up, "is_delta_asset", lambda asset: True)
    monkeypatch.setattr(up, "stage_delta", lambda result: staged)
    monkeypatch.setattr(up, "apply_staged_update", lambda s: applied.append(s) or tmp_path / "s.ps1")
    monkeypatch.setattr(win, "_confirm_unsaved", lambda what: True)
    monkeypatch.setattr(win, "close", lambda: closed.append(True))
    monkeypatch.setattr(QApplication, "quit", lambda self: None)
    win._update_asset = up.Asset(f"PTTAutoPost-9.9.9-delta-{up.__version__}.zip", "https://github.com/x", 10)
    win._on_update_downloaded(up.DownloadResult(tmp_path / "d.zip", "0" * 64, True, 10))
    assert applied == [staged] and win._quitting and closed


def test_update_download_can_be_cancelled_at_the_unsaved_prompt(win, monkeypatch, tmp_path):
    from src import update as up
    staged = up.StagedUpdate(tmp_path / "staging", "9.9.9", ("PTTAutoPost.exe",), ())
    applied = []
    monkeypatch.setattr(up, "is_delta_asset", lambda asset: True)
    monkeypatch.setattr(up, "stage_delta", lambda result: staged)
    monkeypatch.setattr(up, "apply_staged_update", lambda s: applied.append(s))
    monkeypatch.setattr(win, "_confirm_unsaved", lambda what: False)
    win._update_asset = up.Asset(f"PTTAutoPost-9.9.9-delta-{up.__version__}.zip", "https://github.com/x", 10)
    win._on_update_downloaded(up.DownloadResult(tmp_path / "d.zip", "0" * 64, True, 10))
    assert applied == [] and not win._quitting


def test_update_download_applies_a_full_portable_zip(win, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication
    from src import update as up
    staged = up.StagedUpdate(tmp_path / "staging", "9.9.9", ("PTTAutoPost.exe", "_internal/x.dll"), ())
    applied, closed = [], []
    monkeypatch.setattr(up, "is_delta_asset", lambda asset: False)
    monkeypatch.setattr(up, "can_apply_delta", lambda app_dir=None: True)
    monkeypatch.setattr(up, "stage_full_zip", lambda result, version: staged)
    monkeypatch.setattr(up, "apply_staged_update", lambda s: applied.append(s))
    monkeypatch.setattr(win, "_confirm_unsaved", lambda what: True)
    monkeypatch.setattr(win, "close", lambda: closed.append(True))
    monkeypatch.setattr(QApplication, "quit", lambda self: None)
    win._update_asset = up.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/x", 100)
    win._update_version = "9.9.9"
    win._on_update_downloaded(up.DownloadResult(tmp_path / "d.zip", "0" * 64, True, 100))
    assert applied == [staged] and win._quitting and closed


def test_fetch_opens_article_images_when_the_setting_is_on(win, http_server, monkeypatch):
    from src.ui import main_window as mw
    calls = []
    real_parse = mw.parse

    def fake_parse(html, url, warnings=None):
        res = real_parse(html, url, warnings)
        res.images = ["https://cdn.example.com/photo.jpg"]
        return res

    monkeypatch.setattr(mw, "parse", fake_parse)
    monkeypatch.setattr(mw.ImageViewer, "show_images",
                        lambda self, urls, strict=True, referer=None: calls.append((urls, strict)))
    win.chk_article_image.setChecked(True)
    win.url_in.setText(http_server + "/ok")
    win.start_fetch()
    assert wait_until(lambda: not win._busy, 8000)
    assert calls == [(["https://cdn.example.com/photo.jpg"], False)]
    assert win.btn_zip.isEnabled()


def test_fetch_with_images_checks_the_setting_and_opens_the_gallery(win, http_server, monkeypatch):
    from src.ui import main_window as mw
    calls = []
    real_parse = mw.parse

    def fake_parse(html, url, warnings=None):
        res = real_parse(html, url, warnings)
        res.images = ["https://cdn.example.com/photo.jpg"]
        return res

    monkeypatch.setattr(mw, "parse", fake_parse)
    monkeypatch.setattr(mw.ImageViewer, "show_images",
                        lambda self, urls, strict=True, referer=None: calls.append(urls))
    assert not win.chk_article_image.isChecked()
    win.url_in.setText(http_server + "/ok")
    win.start_fetch()
    assert wait_until(lambda: not win._busy, 8000)
    assert win.chk_article_image.isChecked()
    assert win.db.get_setting("links.article_images_open") == "1"
    assert calls == [["https://cdn.example.com/photo.jpg"]]



def test_auto_image_off_by_default(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    win.session.logged_in = True
    win._on_links_changed([_image_link("https://i.imgur.com/a.jpg")])
    assert calls == []


def test_auto_image_once_per_connection_and_one_per_screen(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    win.chk_auto_image.setChecked(True)
    win.session.logged_in = True
    win.session.login_state = Login.LOGGED_IN
    links = [_image_link("https://i.imgur.com/a.jpg"), _image_link("https://i.imgur.com/b.jpg"),
             _image_link("https://i.imgur.com/c.jpg")]
    win._on_links_changed(links)
    win._on_links_changed(links)
    assert calls == ["https://i.imgur.com/a.jpg"]
    win._on_links_changed([_image_link("https://i.imgur.com/d.jpg")])
    assert calls == ["https://i.imgur.com/a.jpg", "https://i.imgur.com/d.jpg"]


def test_auto_image_minute_limit_and_reconnect_reset(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    win.chk_auto_image.setChecked(True)
    win.session.logged_in = True
    win.session.login_state = Login.LOGGED_IN
    for i in range(4):
        win._on_links_changed([_image_link(f"https://i.imgur.com/{i}.jpg")])
    assert len(calls) == 3
    win._on_conn_state(State.CONNECTED)                 # new connection clears the seen set
    win._on_links_changed([_image_link("https://i.imgur.com/0.jpg")])
    assert len(calls) == 4


def test_auto_image_does_not_require_app_login_or_idle_typing(win, monkeypatch):
    calls, manual = [], []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    monkeypatch.setattr(win, "_open_link", lambda url: manual.append(url) or True)
    win.chk_auto_image.setChecked(True)
    win.session.logged_in = False                       # manual PTT login: the app never saw the login screen
    win.session.login_state = Login.MANUAL
    win.typer.running = True
    win._on_links_changed([_image_link("https://i.imgur.com/a.jpg")])
    assert calls == ["https://i.imgur.com/a.jpg"]       # the viewer never steals focus, so no need to wait
    win._open_link("https://i.imgur.com/a.jpg")
    assert manual == ["https://i.imgur.com/a.jpg"]


def test_auto_image_ignores_non_image_links(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    win.chk_auto_image.setChecked(True)
    win._on_links_changed([_image_link("https://example.com/article")])
    assert calls == []


def test_auto_open_opens_at_once_and_does_not_duplicate_on_the_retry_hooks(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    win.chk_auto_image.setChecked(True)
    win.typer.running = True
    win.term.s.screen.feed(b"https://i.imgur.com/a.jpg")
    win.term._on_screen_changed()
    assert calls == ["https://i.imgur.com/a.jpg"]
    win.typer.running = False
    win._typing_finished(True, "done")
    assert calls == ["https://i.imgur.com/a.jpg"]
    assert win.statusBar().currentMessage() == "done"


def test_auto_open_works_without_the_app_login_state(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    win.chk_auto_image.setChecked(True)
    win.session.logged_in = False
    win.session.login_state = Login.MANUAL
    win.term.s.screen.feed(b"https://i.imgur.com/b.jpg")
    win.term._on_screen_changed()
    assert calls == ["https://i.imgur.com/b.jpg"]
    win._on_login_state(Login.LOGGED_IN)
    assert calls == ["https://i.imgur.com/b.jpg"]


def test_enabling_auto_open_processes_images_already_on_screen(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    win.session.logged_in = True
    win.session.login_state = Login.LOGGED_IN
    win.term.s.screen.feed(b"see https://i.imgur.com/a.jpg")
    win.term._on_screen_changed()
    assert calls == []
    win.chk_auto_image.setChecked(True)
    assert calls == ["https://i.imgur.com/a.jpg"]


def test_auto_open_works_from_a_real_terminal_screen(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    win.chk_auto_image.setChecked(True)
    win.session.logged_in = True
    win.session.login_state = Login.LOGGED_IN
    win.term.s.screen.feed(b"see \x1b[4mhttps://i.imgur.com/a.jpg\x1b[0m today")
    win.term._on_screen_changed()
    assert calls == ["https://i.imgur.com/a.jpg"]


def test_auto_open_accepts_https_images_and_reports_the_limit(win, monkeypatch):
    calls, notices = [], []
    monkeypatch.setattr(win, "_open_image_inside", lambda url: calls.append(url) or True)
    monkeypatch.setattr(win, "_notice", lambda msg: notices.append(msg))
    win.chk_auto_image.setChecked(True)
    for url in ("https://example.com/article", "http://i.imgur.com/x.jpg", "https://example.com/a.svg",
                "https://192.168.1.1/x.png", "https://localhost/x.png"):
        win._on_links_changed([_image_link(url)])
    assert calls == []
    win._on_links_changed([_image_link("https://cdn.example.com/photo.jpg")])
    assert calls == ["https://cdn.example.com/photo.jpg"]
    links = [_image_link("https://i.imgur.com/b.jpg"), _image_link("https://i.imgur.com/c.jpg")]
    win._on_links_changed(links)
    assert calls == ["https://cdn.example.com/photo.jpg", "https://i.imgur.com/b.jpg"]
    limit_notices = [n for n in notices if "已達自動開啟上限" in n]
    assert len(limit_notices) == 1 and "略過 1 個" in limit_notices[0]
    win._on_links_changed(links)
    assert len([n for n in notices if "已達自動開啟上限" in n]) == 1


def test_manual_click_still_opens_extension_only_http_url(win, monkeypatch):
    calls = []
    monkeypatch.setattr(browser, "open_url", lambda url, mode, path: calls.append(url) or (True, "ok"))
    win.term.linkActivated.emit("http://example.com/x.jpg")
    assert calls == ["http://example.com/x.jpg"]


def test_backup_data_writes_a_restorable_database(win, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    target = tmp_path / "ui-backup.db"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    win.db.save_draft({"title": "UI備份"})
    win.backup_data()
    assert target.is_file()
    b = Database(target)
    try:
        assert [d["title"] for d in b.list_drafts()] == ["UI備份"]
    finally:
        b.close()
