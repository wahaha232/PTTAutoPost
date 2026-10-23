import pytest

from src.net.session import PttSession
from src.storage.db import Database
from src.ui import main_window as mw
from src.ui.main_window import MainWindow


def make_window(tmp_path):
    db = Database(tmp_path / "sponsor.db")
    return db, MainWindow(db, PttSession())


@pytest.fixture
def empty_win(qapp, tmp_path):
    db, win = make_window(tmp_path)
    yield win
    win.session.disconnect_()
    db.close()


def test_sponsor_block_is_hidden_when_no_url(empty_win):
    assert empty_win.sponsor_box.isHidden()


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


def test_sponsor_block_shows_and_opens_default_browser(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "SPONSOR_URL", "https://example.com/sponsor")
    monkeypatch.setattr(mw, "SPONSOR_TEXT", "Sponsor")
    calls = []
    monkeypatch.setattr(mw.browser, "open_url", lambda url, mode: calls.append((url, mode)) or (True, "opened"))
    db, win = make_window(tmp_path)
    try:
        assert not win.sponsor_box.isHidden()
        assert win.btn_sponsor.text() == "Sponsor"
        win.btn_sponsor.click()
        assert calls == [("https://example.com/sponsor", "system")]
    finally:
        win.session.disconnect_()
        db.close()
