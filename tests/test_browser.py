from pathlib import Path

from src.ui import browser


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ")


def test_detect_browsers_from_common_paths(tmp_path, monkeypatch):
    pf = tmp_path / "ProgramFiles"
    pf86 = tmp_path / "ProgramFilesx86"
    local = tmp_path / "Local"
    _touch(pf / "Google/Chrome/Application/chrome.exe")
    _touch(pf86 / "Microsoft/Edge/Application/msedge.exe")
    _touch(pf / "Mozilla Firefox/firefox.exe")
    monkeypatch.setenv("ProgramFiles", str(pf))
    monkeypatch.setenv("ProgramFiles(x86)", str(pf86))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(browser.shutil, "which", lambda _name: None)
    found = browser.detect_browsers()
    assert found["chrome"] == str(pf / "Google/Chrome/Application/chrome.exe")
    assert found["edge"] == str(pf86 / "Microsoft/Edge/Application/msedge.exe")
    assert found["firefox"] == str(pf / "Mozilla Firefox/firefox.exe")


def test_detect_browsers_falls_back_to_which(monkeypatch):
    monkeypatch.setenv("PROGRAMFILES", "")
    monkeypatch.setenv("PROGRAMFILES(X86)", "")
    monkeypatch.setenv("LOCALAPPDATA", "")
    monkeypatch.setattr(browser.shutil, "which", lambda name: "/usr/bin/firefox" if "firefox" in name else None)
    assert browser.detect_browsers()["firefox"] == "/usr/bin/firefox"


def test_open_url_rejects_unsafe_urls(qapp):
    assert not browser.open_url("ftp://example.com/a")[0]
    assert not browser.open_url("javascript:alert(1)")[0]
    assert not browser.open_url("http://user:pass@example.com/a")[0]


def test_open_url_system_browser(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr(browser.QDesktopServices, "openUrl", staticmethod(lambda url: calls.append(url.toString()) or True))
    ok, _msg = browser.open_url("https://example.com/a")
    assert ok and calls == ["https://example.com/a"]


def test_open_url_custom_browser_passes_url_as_one_argument(qapp, tmp_path, monkeypatch):
    exe = tmp_path / "browser.exe"
    exe.write_bytes(b"MZ")
    calls = []
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    ok, _msg = browser.open_url("https://example.com/a?b=1", "custom", str(exe))
    assert ok
    assert calls[0][0][0] == [str(exe), "https://example.com/a?b=1"]
    assert calls[0][1]["shell"] is False


def test_open_url_reports_missing_browser(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "detect_browsers", lambda: {})
    assert not browser.open_url("https://example.com/a", "chrome")[0]
    assert not browser.open_url("https://example.com/a", "custom", str(tmp_path / "missing.exe"))[0]
