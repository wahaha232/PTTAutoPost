import re
from pathlib import Path

from src.version import BUILD_DATE, __version__
from tools import make_portable as mp

ROOT = Path(__file__).resolve().parent.parent


def test_proprietary_license_exists():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "All rights reserved" in text
    assert "\u5c08\u6709\u6388\u6b0a" in text
    assert "THIRD_PARTY_NOTICES.md" in text


def test_third_party_notices_cover_runtime_dependencies():
    text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for name in ("PySide6", "Qt", "shiboken6", "requests", "beautifulsoup4", "lxml", "charset-normalizer", "Python", "PyInstaller"):
        assert name in text
    assert "LGPL-3.0" in text
    assert "onedir" in text


def test_referenced_license_texts_exist():
    text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"`(licenses/[^`]+)`", text))
    assert referenced
    for rel in referenced:
        assert (ROOT / rel).is_file(), rel


def test_user_readme_has_version_placeholder_and_safety_notes():
    text = (ROOT / "USER_README.txt").read_text(encoding="utf-8")
    assert "{version}" in text and "{build_date}" in text
    assert "SmartScreen" in text
    assert "Ctrl+Shift+C" in text and "Ctrl+Shift+V" in text
    assert "--selftest" in text and "--probe" in text
    assert "D:/Claude" not in text and "D:\\Claude" not in text


def test_spec_builds_a_folder_with_replaceable_qt_libraries():
    text = (ROOT / "PTTAutoPost.spec").read_text(encoding="utf-8")
    assert "exclude_binaries=True" in text
    assert "COLLECT(" in text
    for module in ("PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtSql"):
        assert module in text
    assert "upx=False" in text
    assert "REMOVE_PREFIXES" in text and "opengl32sw.dll" in text
    assert "PySide6/plugins/imageformats/" in text and "PySide6/translations/" in text


def test_readme_text_has_current_version_and_date():
    text = mp.readme_text()
    assert f"PTT AutoPost {__version__}" in text
    assert BUILD_DATE in text
    assert "{version}" not in text and "{build_date}" not in text


def test_assemble_copies_folder_docs_and_writable_data_dirs(monkeypatch, tmp_path):
    build_out = tmp_path / "build"
    app = build_out / "PTTAutoPost"
    (app / "_internal").mkdir(parents=True)
    (app / "PTTAutoPost.exe").write_bytes(b"exe")
    (app / "_internal" / "Qt6Core.dll").write_bytes(b"qt")
    portable = tmp_path / "portable"
    monkeypatch.setattr(mp, "BUILD_OUT", build_out)
    monkeypatch.setattr(mp, "APP_DIR", app)
    monkeypatch.setattr(mp, "PORTABLE", portable)
    assert mp.assemble() == 0
    assert (portable / "PTTAutoPost.exe").is_file()
    assert (portable / "_internal" / "Qt6Core.dll").is_file()
    for name in ("config", "logs", "data"):
        assert (portable / name).is_dir()
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.txt", "licenses/LGPL-3.0.txt"):
        assert (portable / name).is_file(), name
    readme = (portable / "README.txt").read_text(encoding="utf-8")
    assert __version__ in readme and "SmartScreen" in readme


def test_archive_uses_lzma2(monkeypatch, tmp_path):
    portable = tmp_path / "PTTAutoPost-0.0.0-portable"
    portable.mkdir()
    (portable / "PTTAutoPost.exe").write_bytes(b"exe")
    calls = []
    monkeypatch.setattr(mp, "PORTABLE", portable)
    monkeypatch.setattr(mp, "ARCHIVE", tmp_path / "out.7z")
    monkeypatch.setattr(mp, "DIST", tmp_path)
    monkeypatch.setattr(mp, "find_7z", lambda: "7z")
    monkeypatch.setattr(mp.subprocess, "call", lambda cmd, cwd=None: calls.append((cmd, cwd)) or 1)
    assert mp.archive() == 1
    assert calls and "-t7z" in calls[0][0] and "-m0=lzma2" in calls[0][0]
    assert calls[0][1] == tmp_path


def test_installer_is_refused_cleanly_without_inno_setup(monkeypatch):
    monkeypatch.setattr(mp, "find_iscc", lambda: "")
    assert mp.installer() == 2


def test_installer_script_keeps_user_data_and_uses_lzma2():
    text = (ROOT / "tools" / "PTTAutoPost.iss").read_text(encoding="utf-8")
    assert "Compression=lzma2/max" in text
    assert "PrivilegesRequired=lowest" in text
    assert "uninsneveruninstall" in text
    assert 'Excludes: "config\\*,logs\\*,data\\*"' in text
    assert "LicenseFile=" in text and "THIRD_PARTY_NOTICES.md" in text
