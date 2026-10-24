import re
import zipfile
from pathlib import Path

from src.version import BUILD_DATE, __version__
from tools import make_portable as mp
from tools import spec_filters

ROOT = Path(__file__).resolve().parent.parent


def test_proprietary_license_exists():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "All rights reserved" in text
    assert "\u5c08\u6709\u6388\u6b0a" in text
    assert "THIRD_PARTY_NOTICES.md" in text
    assert "LGPL" in text and "Qt" in text
    assert "\u4e0d\u69cb\u6210\u6cd5\u5f8b\u5efa\u8b70" in text


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
    assert "filter_entries" in text and "ONEFILE" in text


def test_spec_filters_keep_platform_tls_and_one_openssl_copy():
    entries = [
        ("PySide6/plugins/platforms/qwindows.dll", "qwindows", "BINARY"),
        ("PySide6/plugins/platforms/qdirect2d.dll", "qdirect2d", "BINARY"),
        ("PySide6/plugins/tls/qopensslbackend.dll", "qopenssl", "BINARY"),
        ("PySide6/plugins/tls/qschannelbackend.dll", "qschannel", "BINARY"),
        ("PySide6/plugins/imageformats/qjpeg.dll", "qjpeg", "BINARY"),
        ("PySide6/plugins/imageformats/qgif.dll", "qgif", "BINARY"),
        ("PySide6/plugins/imageformats/qwebp.dll", "qwebp", "BINARY"),
        ("PySide6/plugins/imageformats/qsvg.dll", "qsvg", "BINARY"),
        ("PySide6/plugins/imageformats/qtiff.dll", "qtiff", "BINARY"),
        ("PySide6/Qt6Quick.dll", "quick", "BINARY"),
        ("PySide6/translations/qtbase_zh_TW.qm", "qm", "DATA"),
        ("PySide6/translations/qtbase_zh_CN.qm", "qmcn", "DATA"),
        ("libcrypto-3.dll", "crypto", "BINARY"),
        ("PySide6/libcrypto-3.dll", "crypto2", "BINARY"),
        ("libssl-3.dll", "ssl", "BINARY"),
        ("PySide6/libssl-3.dll", "ssl2", "BINARY"),
    ]
    kept = spec_filters.filter_entries(entries)
    names = [spec_filters.normalize(e[0]) for e in kept]
    assert "PySide6/plugins/platforms/qwindows.dll" in names
    assert "PySide6/plugins/tls/qopensslbackend.dll" in names
    assert "PySide6/plugins/tls/qschannelbackend.dll" in names
    assert "PySide6/plugins/imageformats/qjpeg.dll" in names
    assert "PySide6/plugins/imageformats/qgif.dll" in names
    assert "PySide6/plugins/imageformats/qwebp.dll" in names
    assert "PySide6/plugins/imageformats/qsvg.dll" not in names
    assert "PySide6/plugins/imageformats/qtiff.dll" not in names
    assert "PySide6/Qt6Quick.dll" not in names
    assert "PySide6/translations/qtbase_zh_TW.qm" in names
    assert "PySide6/translations/qtbase_zh_CN.qm" not in names
    assert names.count("libcrypto-3.dll") == 1
    assert names.count("libssl-3.dll") == 1
    assert "libcrypto-3.dll" in names and "libssl-3.dll" in names


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


def test_layout_report_requires_qwindows_and_tls_plugins(tmp_path):
    internal = tmp_path / "_internal"
    (internal / "PySide6/plugins/platforms").mkdir(parents=True)
    (internal / "PySide6/plugins/tls").mkdir(parents=True)
    (internal / "Qt6Core.dll").write_bytes(b"qt")
    (internal / "PySide6/plugins/platforms/qwindows.dll").write_bytes(b"q")
    (internal / "PySide6/plugins/tls/qopensslbackend.dll").write_bytes(b"t")
    report = mp.layout_report(tmp_path)
    assert report["replaceable"] and report["platform"] and report["tls"]
    (internal / "PySide6/plugins/platforms/qwindows.dll").unlink()
    assert not mp.layout_report(tmp_path)["platform"]
    (internal / "PySide6/plugins/tls/qopensslbackend.dll").unlink()
    assert not mp.layout_report(tmp_path)["tls"]
    assert mp.layout_report(tmp_path, onefile=True)["platform"]


def test_onefile_build_sets_the_environment_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(mp.subprocess, "call", lambda cmd, cwd=None, env=None: calls.append((cmd, cwd, env)) or 0)
    assert mp.build(onefile=True) == 0
    assert calls and calls[0][2]["PTTAUTOPOST_ONEFILE"] == "1"
    assert mp.build(onefile=False) == 0
    assert calls[-1][2]["PTTAUTOPOST_ONEFILE"] == "0"


def test_assemble_onefile_copies_the_exe_and_docs(monkeypatch, tmp_path):
    build_out = tmp_path / "build"
    build_out.mkdir()
    (build_out / "PTTAutoPost.exe").write_bytes(b"exe")
    portable = tmp_path / "portable"
    monkeypatch.setattr(mp, "BUILD_OUT", build_out)
    monkeypatch.setattr(mp, "PORTABLE", portable)
    assert mp.assemble(onefile=True) == 0
    assert (portable / "PTTAutoPost.exe").is_file()
    assert not (portable / "_internal").exists()
    for name in ("config", "logs", "data", "LICENSE", "THIRD_PARTY_NOTICES.md", "README.txt", "licenses/LGPL-3.0.txt"):
        assert (portable / name).exists(), name
    assert "onefile" in (portable / "README.txt").read_text(encoding="utf-8")


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


def test_archive_falls_back_to_zip_without_7zip(monkeypatch, tmp_path):
    portable = tmp_path / "PTTAutoPost-0.0.0-portable"
    portable.mkdir()
    (portable / "PTTAutoPost.exe").write_bytes(b"exe")
    (portable / "README.txt").write_text("readme", encoding="utf-8")
    monkeypatch.setattr(mp, "PORTABLE", portable)
    monkeypatch.setattr(mp, "DIST", tmp_path)
    monkeypatch.setattr(mp, "ARCHIVE", tmp_path / "out.7z")
    monkeypatch.setattr(mp, "ZIP_ARCHIVE", tmp_path / "PTTAutoPost-0.0.0-portable.zip")
    monkeypatch.setattr(mp, "find_7z", lambda: "")
    assert mp.archive() == 0
    zips = list(tmp_path.glob("*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as z:
        assert "PTTAutoPost-0.0.0-portable/PTTAutoPost.exe" in z.namelist()


def test_installer_is_refused_cleanly_without_inno_setup(monkeypatch):
    monkeypatch.setattr(mp, "find_iscc", lambda: "")
    assert mp.installer() == 2


def test_source_listing_collects_code_and_skips_build_outputs(tmp_path):
    from tools import make_source_listing as listing
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('x')\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "generated.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    files = [p.relative_to(tmp_path).as_posix() for p in listing.collect_files(tmp_path)]
    assert files == ["src/app.py"]


def test_installer_script_keeps_user_data_and_uses_lzma2():
    text = (ROOT / "tools" / "PTTAutoPost.iss").read_text(encoding="utf-8")
    assert "Compression=lzma2/max" in text
    assert "PrivilegesRequired=lowest" in text
    assert "uninsneveruninstall" in text
    assert 'Excludes: "config\\*,logs\\*,data\\*"' in text
    assert "LicenseFile=" in text and "THIRD_PARTY_NOTICES.md" in text
    assert "[InstallDelete]" in text
    assert 'Type: filesandordirs; Name: "{app}\\_internal"' in text
