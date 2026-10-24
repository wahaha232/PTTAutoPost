"""Check GitHub Releases and download an update asset.

This module never installs or runs a downloaded file. The UI asks the user, downloads to
an updates folder, verifies the SHA-256 digest when GitHub provides one, and then tells
the user how to finish the update (portable ZIP or installed setup.exe).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from .logging_setup import get_logger
from .version import __version__

log = get_logger("update")
GITHUB_REPO = "wahaha232/PTTAutoPost"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"PTTAutoPost/{__version__}"
MAX_RELEASE_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 300 * 1024 * 1024
ALLOWED_HOSTS = {"api.github.com", "github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com", "github-releases.githubusercontent.com"}
TOKEN_ENV = "PTTAUTOPOST_GITHUB_TOKEN"


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int
    digest: str = ""


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    name: str
    notes: str
    html_url: str
    assets: tuple[Asset, ...]


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    verified: bool
    size: int


def parse_version(tag: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"[vV]?(\d+)\.(\d+)\.(\d+)", (tag or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def github_token() -> str | None:
    return os.environ.get(TOKEN_ENV, "").strip() or None


def _allowed_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return (p.scheme == "https" and (p.hostname or "").lower() in ALLOWED_HOSTS
                and not p.username and not p.password)
    except ValueError:
        return False


def _headers(token: str | None = None) -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT,
         "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _read_limited(resp, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise UpdateError("GitHub 回應超過大小上限，已停止。")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_latest_release(token: str | None = None, timeout: float = 15) -> Release:
    try:
        resp = requests.get(LATEST_RELEASE_API, headers=_headers(token), timeout=timeout)
    except requests.RequestException:
        raise UpdateError("無法連線到 GitHub 檢查更新；請確認網路後再試。") from None
    try:
        if resp.status_code == 404:
            raise UpdateError(
                f"GitHub 上找不到 {GITHUB_REPO} 的公開 Release。若儲存庫是私人，"
                f"請設定環境變數 {TOKEN_ENV}（只用在 GitHub API，不會儲存或寫入日誌）。")
        if resp.status_code in (401, 403):
            raise UpdateError("GitHub 拒絕存取更新資訊（可能是私人儲存庫、Token 無效或 API 次數上限）。")
        if resp.status_code != 200:
            raise UpdateError(f"GitHub 更新檢查失敗（HTTP {resp.status_code}）。")
        raw = _read_limited(resp, MAX_RELEASE_BYTES)
    finally:
        resp.close()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise UpdateError("GitHub 回傳的更新資訊格式不正確。") from None
    if not isinstance(data, dict):
        raise UpdateError("GitHub 回傳的更新資訊格式不正確。")
    tag = str(data.get("tag_name") or "")
    version = parse_version(tag)
    if version is None:
        raise UpdateError(f"最新 Release 的版本標籤無法辨識：{tag or '(空白)'}。")
    assets = []
    for item in data.get("assets") or []:
        if not isinstance(item, dict):
            continue
        name, url = str(item.get("name") or ""), str(item.get("browser_download_url") or "")
        if name and _allowed_url(url):
            try:
                size = max(0, int(item.get("size") or 0))
            except (TypeError, ValueError):
                size = 0
            assets.append(Asset(name=name, url=url, size=size, digest=str(item.get("digest") or "")))
    return Release(version=".".join(str(n) for n in version), tag=tag, name=str(data.get("name") or tag),
                   notes=str(data.get("body") or ""), html_url=str(data.get("html_url") or ""),
                   assets=tuple(assets))


def choose_asset(assets: tuple[Asset, ...] | list[Asset], installed: bool) -> Asset | None:
    suffixes = ("-setup.exe",) if installed else ("-portable.zip", "-portable.7z")
    for suffix in suffixes:
        for asset in assets:
            if asset.name.lower().endswith(suffix) and _allowed_url(asset.url):
                return asset
    return None


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_installed(app_dir: Path | None = None) -> bool:
    return any((app_dir or application_dir()).glob("unins*.exe"))


def updates_dir() -> Path:
    candidates = [application_dir() / "updates",
                  Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "PTT AutoPost" / "updates"]
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return d
        except OSError:
            continue
    raise UpdateError("找不到可寫入的資料夾來存放更新檔。")


def download_asset(asset: Asset, dest: Path | None = None, token: str | None = None,
                   timeout: float = 30, progress=None) -> DownloadResult:
    if not _allowed_url(asset.url):
        raise UpdateError("更新檔網址不是允許的 GitHub HTTPS 網址，已拒絕下載。")
    safe_name = Path(asset.name).name
    if not safe_name or safe_name != asset.name:
        raise UpdateError("更新檔名稱不正確，已拒絕下載。")
    folder = dest or updates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe_name
    part = target.with_name(target.name + ".part")
    expected = ""
    digest = (asset.digest or "").strip().lower()
    if digest.startswith("sha256:"):
        expected = digest.split(":", 1)[1]
    elif re.fullmatch(r"[0-9a-f]{64}", digest):
        expected = digest
    h = hashlib.sha256()
    total = 0
    try:
        resp = requests.get(asset.url, headers=_headers(token), timeout=timeout, stream=True)
        try:
            if resp.status_code != 200:
                raise UpdateError(f"下載更新檔失敗（HTTP {resp.status_code}）。")
            final_url = getattr(resp, "url", "") or ""
            if final_url and not _allowed_url(final_url):
                raise UpdateError("下載被重新導向到不允許的網址，已停止。")
            declared = int(getattr(resp, "headers", {}).get("Content-Length") or 0)
            if declared > MAX_ASSET_BYTES:
                raise UpdateError("更新檔超過大小上限，已停止下載。")
            with open(part, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_ASSET_BYTES:
                        raise UpdateError("更新檔超過大小上限，已停止下載。")
                    h.update(chunk)
                    f.write(chunk)
                    if progress:
                        progress(total, max(declared, asset.size or 0))
        finally:
            resp.close()
        if asset.size and total != asset.size:
            raise UpdateError(f"更新檔大小不符（預期 {asset.size} bytes，實際 {total} bytes）。")
        actual = h.hexdigest()
        if expected and actual != expected:
            raise UpdateError("更新檔 SHA-256 驗證失敗，已刪除下載檔。")
        os.replace(part, target)
        return DownloadResult(path=target, sha256=actual, verified=bool(expected), size=total)
    except requests.RequestException:
        part.unlink(missing_ok=True)
        raise UpdateError("下載更新檔時網路中斷。") from None
    except Exception:
        part.unlink(missing_ok=True)
        raise
