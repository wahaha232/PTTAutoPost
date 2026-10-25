from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from src import update
from src.net.session import PttSession
from src.storage.db import Database
from src.ui import main_window as mw
from src.ui.main_window import MainWindow
from src.version import __version__


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    db = Database(tmp_path / "update.db")
    window = MainWindow(db, PttSession())
    yield window
    window.session.disconnect_()
    db.close()


def make_release(version="9.9.9", assets=None):
    assets = assets or (
        update.Asset("PTTAutoPost-9.9.9-portable.zip",
                     "https://github.com/wahaha232/PTTAutoPost/releases/download/v9.9.9/x.zip", 2048),
        update.Asset("PTTAutoPost-9.9.9-setup.exe",
                     "https://github.com/wahaha232/PTTAutoPost/releases/download/v9.9.9/x.exe", 4096),
    )
    return update.Release(version=version, tag=f"v{version}", name=f"Release {version}",
                          notes="修正內容", html_url="https://github.com/wahaha232/PTTAutoPost/releases",
                          assets=assets)


def test_update_controls_and_menu_exist(win):
    assert win.btn_update_check.text() == "檢查更新"
    assert win.btn_update_force.text() == "強制更新"
    assert win.btn_update_manual.text() == "手動下載"
    assert win.act_check_update.text() == "檢查更新…"
    assert win.act_force_update.text() == "強制更新…"
    assert win.act_manual_download.text() == "手動下載…"
    assert "關於" in win.act_about.text()
    assert "贊助" in win.act_sponsor.text()
    assert win.chk_auto_update.isChecked()
    assert not win.update_progress.isVisible()
    assert __version__ in win.lbl_update_status.text()


def test_auto_check_with_no_update_is_silent(win, monkeypatch):
    infos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: infos.append(a[2]) or QMessageBox.StandardButton.Ok))
    win._update_auto, win._update_phase = True, "check"
    win._on_update_release(make_release("0.0.1"))
    assert infos == []
    assert "最新" in win.lbl_update_status.text()


def test_auto_check_failure_is_silent_but_shown_in_status(win, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2]) or QMessageBox.StandardButton.Ok))
    win._update_auto, win._update_phase = True, "check"
    win._on_update_error("背景檢查失敗")
    assert warnings == []
    assert "失敗" in win.lbl_update_status.text()


def test_force_update_accepts_the_current_version(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    started = []
    monkeypatch.setattr(win, "_start_update_download", lambda asset: started.append(asset))
    win._update_force = True
    win._on_update_release(make_release(__version__))
    assert started and started[0].name.endswith("-portable.zip")


def test_update_progress_bar_tracks_download(win):
    win.update_progress.setVisible(True)
    win._on_update_progress(5, 10)
    assert win.update_progress.maximum() == 10 and win.update_progress.value() == 5
    win._update_asset = update.Asset("x.zip", "https://github.com/x.zip", 1)
    win._on_update_downloaded(update.DownloadResult(path=Path("x.zip"), sha256="a" * 64, verified=False, size=1))
    assert not win.update_progress.isVisible()


def test_manual_download_opens_github_releases(win, monkeypatch):
    opened = []
    monkeypatch.setattr("src.ui.main_window.QDesktopServices.openUrl", lambda url: opened.append(url.toString()) or True)
    win.open_manual_download()
    assert opened == [update.RELEASES_PAGE]


def test_about_dialog_has_version_and_license(win, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "about", staticmethod(lambda *a, **k: shown.append(a[2])))
    win.show_about()
    assert shown and __version__ in shown[-1] and "LGPL" in shown[-1]


def test_sponsor_menu_explains_missing_link(win, monkeypatch):
    infos = []
    monkeypatch.setattr(mw, "SPONSOR_URL", "")
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: infos.append(a[2]) or QMessageBox.StandardButton.Ok))
    win.act_sponsor.trigger()
    assert infos and "贊助" in infos[-1]


def test_latest_version_shows_information(win, monkeypatch):
    infos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: infos.append(a[2]) or QMessageBox.StandardButton.Ok))
    win._on_update_release(make_release("0.0.1"))
    assert infos and "已是最新版本" in infos[-1]
    assert not win._update_busy


def test_newer_release_prompts_and_can_be_cancelled(win, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No))
    started = []
    monkeypatch.setattr(win, "_start_update_download", lambda asset: started.append(asset))
    win._on_update_release(make_release())
    assert asked and "PTTAutoPost-9.9.9-portable.zip" in asked[-1]
    assert started == []


def test_newer_release_selects_portable_zip_and_starts_download(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(update, "is_installed", lambda: False)
    started = []
    monkeypatch.setattr(win, "_start_update_download", lambda asset: started.append(asset))
    win._on_update_release(make_release())
    assert started and started[0].name.endswith("-portable.zip")


def test_newer_release_selects_setup_for_installed_copy(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(update, "is_installed", lambda: True)
    started = []
    monkeypatch.setattr(win, "_start_update_download", lambda asset: started.append(asset))
    win._on_update_release(make_release())
    assert started and started[0].name.endswith("-setup.exe")


def test_release_without_matching_asset_explains_and_does_not_download(win, monkeypatch):
    infos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: infos.append(a[2]) or QMessageBox.StandardButton.Ok))
    started = []
    monkeypatch.setattr(win, "_start_update_download", lambda asset: started.append(asset))
    win._on_update_release(make_release(assets=(update.Asset("notes.txt", "https://github.com/x.txt", 1),)))
    assert infos and "9.9.9" in infos[-1] and "Release" in infos[-1]
    assert started == []


def test_downloaded_asset_message_explains_manual_install(win, monkeypatch, tmp_path):
    infos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: infos.append(a[2]) or QMessageBox.StandardButton.Ok))
    win._update_asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/x.zip", 3)
    path = tmp_path / "PTTAutoPost-9.9.9-portable.zip"
    path.write_bytes(b"abc")
    win._on_update_downloaded(update.DownloadResult(path=path, sha256="a" * 64, verified=True, size=3))
    assert infos and str(path) in infos[-1] and "不會自動執行" in infos[-1]
    assert not win._update_busy


def test_update_error_shows_warning(win, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2]) or QMessageBox.StandardButton.Ok))
    win._on_update_error("網路失敗")
    assert warnings and "網路失敗" in warnings[-1]
    assert not win._update_busy


def test_open_update_folder_uses_the_updates_directory(win, monkeypatch, tmp_path):
    opened, notices = [], []
    monkeypatch.setattr(update, "updates_dir", lambda: tmp_path)
    monkeypatch.setattr("src.ui.main_window.QDesktopServices.openUrl", lambda url: opened.append(url.toString()) or True)
    monkeypatch.setattr(win, "_notice", lambda msg: notices.append(msg))
    win.open_update_folder()
    assert opened and opened[0].startswith("file:")
    assert notices and str(tmp_path) in notices[-1]


def test_download_verification_wording_is_explicit(win, monkeypatch, tmp_path):
    infos = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: infos.append(a[2]) or QMessageBox.StandardButton.Ok))
    path = tmp_path / "x.zip"
    path.write_bytes(b"x")
    win._update_asset = update.Asset("x.zip", "https://github.com/x.zip", 1)
    win._on_update_downloaded(update.DownloadResult(path=path, sha256="a" * 64, verified=True, size=1))
    assert "已核對" in infos[-1] and "不代表發布者身分" in infos[-1]
    win._on_update_downloaded(update.DownloadResult(path=path, sha256="", verified=False, size=1))
    assert "未提供 digest" in infos[-1] and "未完成雜湊核對" in infos[-1]


def test_update_check_is_ignored_while_busy(win, monkeypatch):
    notices = []
    monkeypatch.setattr(win, "_notice", lambda msg: notices.append(msg))
    win._update_busy = True
    win.check_updates()
    assert notices and "進行中" in notices[-1]
