"""Detect installed browsers and open an already validated http/https URL.

No shell is used: a configured browser always receives the URL as one argument.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ..links import validate_http_url

BROWSER_CHOICES = (
    ("system", "系統預設瀏覽器"),
    ("chrome", "Google Chrome"),
    ("edge", "Microsoft Edge"),
    ("firefox", "Mozilla Firefox"),
    ("custom", "自訂執行檔"),
)
BROWSER_KEYS = tuple(k for k, _ in BROWSER_CHOICES)
BROWSER_LABELS = dict(BROWSER_CHOICES)


def _candidate_paths() -> dict[str, list[Path]]:
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    return {
        "chrome": [
            Path(local) / "Google/Chrome/Application/chrome.exe" if local else None,
            Path(pf) / "Google/Chrome/Application/chrome.exe" if pf else None,
            Path(pf86) / "Google/Chrome/Application/chrome.exe" if pf86 else None,
        ],
        "edge": [
            Path(pf86) / "Microsoft/Edge/Application/msedge.exe" if pf86 else None,
            Path(pf) / "Microsoft/Edge/Application/msedge.exe" if pf else None,
        ],
        "firefox": [
            Path(pf) / "Mozilla Firefox/firefox.exe" if pf else None,
            Path(pf86) / "Mozilla Firefox/firefox.exe" if pf86 else None,
        ],
    }


def detect_browsers() -> dict[str, str]:
    """Return {chrome/edge/firefox: executable path} for browsers found on this machine."""
    found: dict[str, str] = {}
    for key, paths in _candidate_paths().items():
        for path in paths:
            if path is not None and path.is_file():
                found[key] = str(path)
                break
    which_names = {
        "chrome": ("chrome", "chrome.exe", "google-chrome", "chromium"),
        "edge": ("msedge", "msedge.exe", "microsoft-edge"),
        "firefox": ("firefox", "firefox.exe"),
    }
    for key, names in which_names.items():
        if key in found:
            continue
        for name in names:
            exe = shutil.which(name)
            if exe:
                found[key] = exe
                break
    return found


def open_url(url: str, mode: str = "system", custom_path: str = "") -> tuple[bool, str]:
    """Open a validated URL. Returns (ok, message); never uses a shell."""
    if not validate_http_url(url):
        return False, "只允許不含帳密的 http/https 網址。"
    mode = mode if mode in BROWSER_KEYS else "system"
    if mode == "system":
        if QDesktopServices.openUrl(QUrl(url)):
            return True, "已用系統瀏覽器開啟連結。"
        return False, "無法用系統瀏覽器開啟連結。"

    if mode == "custom":
        exe = (custom_path or "").strip()
    else:
        exe = detect_browsers().get(mode, "")
    if not exe:
        return False, f"找不到 {BROWSER_LABELS.get(mode, mode)} 的執行檔；請改用系統瀏覽器或指定路徑。"
    path = Path(exe)
    if not path.is_file() or (os.name == "nt" and path.suffix.lower() != ".exe"):
        return False, f"瀏覽器執行檔不存在或格式不正確：{exe}"
    try:
        subprocess.Popen([str(path), url], cwd=str(path.parent), close_fds=True, shell=False)
    except OSError as e:
        return False, f"無法啟動瀏覽器：{e}"
    return True, f"已用 {BROWSER_LABELS.get(mode, mode)} 開啟連結。"
