import re
from pathlib import Path

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
