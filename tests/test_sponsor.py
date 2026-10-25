from PySide6.QtWidgets import QLabel, QPushButton

from src.net.session import PttSession
from src.storage.db import Database
from src.ui import main_window as mw
from src.ui.main_window import MainWindow


def click_sponsor_link(win):
    dialog = win.sponsor_dialog
    assert dialog is not None and dialog.isVisible()
    link = dialog.findChild(QPushButton, "sponsorLink")
    assert link is not None
    link.click()
    return dialog


def make_window(tmp_path):
    db = Database(tmp_path / "sponsor.db")
    return db, MainWindow(db, PttSession())


def test_sponsor_block_is_hidden_when_no_url(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "SPONSOR_URL", "")
    db, win = make_window(tmp_path)
    try:
        assert win.sponsor_box.isHidden()
    finally:
        win.session.disconnect_()
        db.close()


def test_sponsor_block_is_hidden_for_invalid_url(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "SPONSOR_URL", "javascript:alert(1)")
    db, win = make_window(tmp_path)
    try:
        assert win.sponsor_box.isHidden()
    finally:
        win.session.disconnect_()
        db.close()


def test_sponsor_block_is_hidden_for_credentials_url(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "SPONSOR_URL", "https://user:pass@example.com/sponsor")
    db, win = make_window(tmp_path)
    try:
        assert win.sponsor_box.isHidden()
    finally:
        win.session.disconnect_()
        db.close()


def test_configured_sponsor_shows_thanks_before_opening(qapp, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(mw.browser, "open_url", lambda url, mode: calls.append((url, mode)) or (True, "opened"))
    db, win = make_window(tmp_path)
    try:
        assert not win.sponsor_box.isHidden()
        assert win.btn_sponsor.text() == "☕ Buy me a coffee"
        win.btn_sponsor.click()
        assert calls == []                              # clicking the settings button only opens the dialog
        dialog = win.sponsor_dialog
        assert dialog is not None and dialog.isVisible()
        texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert "謝謝你請我喝咖啡！" in texts
        assert "非常感謝你的慷慨贊助" in texts
        assert "每一杯透過 Buy Me a Coffee 送來的咖啡" in texts
        assert "用心改進各項功能與體驗，提供更順暢、穩定的環境" in texts
        assert "希望這款軟體能持續在日常中為你帶來幫助" in texts
        link = dialog.findChild(QPushButton, "sponsorLink")
        assert link is not None
        assert "Buy me a coffee" in link.accessibleName()
        assert not link.icon().isNull() and link.iconSize().width() == 320
    finally:
        win.session.disconnect_()
        db.close()


def test_sponsor_menu_shows_thanks_dialog(qapp, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(mw.browser, "open_url", lambda url, mode: calls.append((url, mode)) or (True, "opened"))
    db, win = make_window(tmp_path)
    try:
        win.act_sponsor.trigger()
        assert calls == [] and win.sponsor_dialog is not None and win.sponsor_dialog.isVisible()
        win.sponsor_dialog.reject()
    finally:
        win.session.disconnect_()
        db.close()


def test_sponsor_link_opens_configured_browser(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "SPONSOR_URL", "https://example.com/sponsor")
    monkeypatch.setattr(mw, "SPONSOR_TEXT", "Sponsor")
    calls = []
    monkeypatch.setattr(mw.browser, "open_url", lambda url, mode: calls.append((url, mode)) or (True, "opened"))
    db, win = make_window(tmp_path)
    try:
        assert not win.sponsor_box.isHidden()
        assert win.btn_sponsor.text() == "Sponsor"
        win.btn_sponsor.click()
        assert calls == []
        click_sponsor_link(win)
        assert calls == [("https://example.com/sponsor", "system")]
    finally:
        win.session.disconnect_()
        db.close()
