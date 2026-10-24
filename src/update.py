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
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
MAX_DELTA_FILE_BYTES = 100 * 1024 * 1024
DELTA_RE = re.compile(r"^PTTAutoPost-(\d+\.\d+\.\d+)-delta-(\d+\.\d+\.\d+)\.zip$", re.I)
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


@dataclass(frozen=True)
class StagedUpdate:
    folder: Path
    version: str
    files: tuple[str, ...]
    deletes: tuple[str, ...]


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


def choose_asset(assets: tuple[Asset, ...] | list[Asset], installed: bool,
                 current: str = __version__, prefer_delta: bool = True) -> Asset | None:
    if not installed and prefer_delta and can_apply_delta():
        for asset in assets:
            match = DELTA_RE.match(asset.name)
            if match and match.group(2) == current and _allowed_url(asset.url):
                return asset
    suffixes = ("-setup.exe",) if installed else ("-portable.zip", "-portable.7z")
    for suffix in suffixes:
        for asset in assets:
            if asset.name.lower().endswith(suffix) and _allowed_url(asset.url):
                return asset
    return None


def is_delta_asset(asset: Asset | None) -> bool:
    return bool(asset is not None and DELTA_RE.match(asset.name))


def can_apply_delta(app_dir: Path | None = None) -> bool:
    """Delta updates need a writable portable folder (not an installed setup copy)."""
    if not getattr(sys, "frozen", False):
        return False
    app = app_dir or application_dir()
    if not (app / "PTTAutoPost.exe").is_file() or is_installed(app):
        return False
    try:
        probe = app / ".update_write_test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _safe_rel(raw: str) -> PurePosixPath:
    name = str(raw or "").replace("\\", "/")
    rel = PurePosixPath(name)
    if (not name or rel.is_absolute() or ".." in rel.parts or any(not part for part in rel.parts)
            or name.startswith("/")):
        raise UpdateError("更新檔含有不安全的檔案路徑，已停止。")
    return rel


def stage_delta(result: DownloadResult) -> "StagedUpdate":
    """Validate the delta ZIP and unpack only its manifest files into a staging folder."""
    digest = (result.sha256 or "").lower()
    if not result.verified:
        raise UpdateError("更新檔沒有可核對的 SHA-256，已停止套用。")
    try:
        with zipfile.ZipFile(result.path) as zf:
            names = set(zf.namelist())
            if "update.json" not in names:
                raise UpdateError("更新檔缺少 update.json，已停止套用。")
            try:
                manifest = json.loads(zf.read("update.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise UpdateError("更新檔的 update.json 格式不正確。") from None
            if not isinstance(manifest, dict) or manifest.get("format") != 1:
                raise UpdateError("更新檔格式不受支援。")
            version, base = str(manifest.get("version") or ""), str(manifest.get("base") or "")
            if base != __version__:
                raise UpdateError(f"這個更新檔是給 {base or '未知版本'} 用的，目前版本是 {__version__}。")
            files = manifest.get("files")
            if not isinstance(files, list) or not files:
                raise UpdateError("更新檔沒有要套用的檔案。")
            staging = updates_dir() / f"staging-{version}"
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            total = 0
            staged: list[str] = []
            for item in files:
                if not isinstance(item, dict):
                    raise UpdateError("更新檔清單格式不正確。")
                rel = _safe_rel(item.get("path"))
                expected = str(item.get("sha256") or "").lower()
                try:
                    size = int(item.get("size") or 0)
                except (TypeError, ValueError):
                    raise UpdateError("更新檔清單的大小格式不正確。") from None
                if size > MAX_DELTA_FILE_BYTES:
                    raise UpdateError(f"更新檔中的 {rel} 過大，已停止。")
                try:
                    data = zf.read(rel.as_posix())
                except KeyError:
                    raise UpdateError(f"更新檔缺少 {rel}，已停止。") from None
                if len(data) != size or hashlib.sha256(data).hexdigest() != expected:                    raise UpdateError(f"更新檔中的 {rel} 驗證失敗，已停止。")
                total += len(data)
                if total > MAX_ASSET_BYTES:
                    raise UpdateError("更新檔內容超過大小上限，已停止。")
                dest = staging.joinpath(*rel.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                staged.append(rel.as_posix())
            deletes = []
            for raw in manifest.get("delete") or []:
                deletes.append(_safe_rel(raw).as_posix())
            if not staged:
                raise UpdateError("更新檔沒有可套用的檔案。")
            return StagedUpdate(staging, version, tuple(staged), tuple(deletes))
    except zipfile.BadZipFile:
        raise UpdateError("更新檔不是有效的 ZIP。") from None
    finally:
        result.path.unlink(missing_ok=True)


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def stage_full_zip(result: DownloadResult, version: str) -> "StagedUpdate":
    """Validate a full portable ZIP and unpack the program files (never config/data/logs/updates)."""
    if not result.verified:
        raise UpdateError("更新檔沒有可核對的 SHA-256，已停止套用。")
    staging = updates_dir() / f"staging-{version}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    total = 0
    try:
        with zipfile.ZipFile(result.path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            if not infos:
                raise UpdateError("更新檔是空的。")
            tops = {PurePosixPath(i.filename.replace("\\", "/")).parts[0] for i in infos}
            prefix = ""
            if len(tops) == 1:
                top = next(iter(tops))
                if any(PurePosixPath(i.filename.replace("\\", "/")).parts[1:] == ("PTTAutoPost.exe",)
                       for i in infos):
                    prefix = top + "/"
            for info in infos:
                name = info.filename.replace("\\", "/")
                if prefix and name.startswith(prefix):
                    name = name[len(prefix):]
                rel = _safe_rel(name)
                if rel.parts[0].lower() in ("config", "data", "logs", "updates"):
                    continue                                  # user data is never replaced
                if info.file_size > 250 * 1024 * 1024:
                    raise UpdateError(f"更新檔中的 {rel} 過大，已停止。")
                data = zf.read(info)
                if len(data) != info.file_size:
                    raise UpdateError(f"更新檔中的 {rel} 大小不符，已停止。")
                total += len(data)
                if total > MAX_ASSET_BYTES:
                    raise UpdateError("更新檔內容超過大小上限，已停止。")
                dest = staging.joinpath(*rel.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                files.append(rel.as_posix())
            if "PTTAutoPost.exe" not in files:
                raise UpdateError("更新檔沒有 PTTAutoPost.exe，已停止。")
            return StagedUpdate(staging, version, tuple(files), ())
    except zipfile.BadZipFile:
        raise UpdateError("更新檔不是有效的 ZIP。") from None
    finally:
        result.path.unlink(missing_ok=True)


def apply_staged_update(staged: "StagedUpdate", app_dir: Path | None = None) -> Path:
    """Write a helper script that waits for this process, applies the staged files, and restarts the app."""
    app = (app_dir or application_dir()).resolve()
    if not (app / "PTTAutoPost.exe").is_file():
        raise UpdateError("找不到 PTTAutoPost.exe，無法套用更新。")
    if is_installed(app):
        raise UpdateError("這是安裝版；請使用 setup.exe 更新。")
    backup = updates_dir() / f"backup-{staged.version}"
    backup.mkdir(parents=True, exist_ok=True)
    script = updates_dir() / f"apply-{staged.version}.ps1"
    files_ps = ", ".join(_ps_quote(f) for f in staged.files)
    deletes_ps = ", ".join(_ps_quote(f) for f in staged.deletes)
    body = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {os.getpid()}
while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 400 }}
$base = {_ps_quote(str(app))}
$staging = {_ps_quote(str(staged.folder))}
$backup = {_ps_quote(str(backup))}
try {{
  foreach ($f in @({files_ps})) {{
    $src = Join-Path -Path $staging -ChildPath $f
    $dst = Join-Path -Path $base -ChildPath $f
    if (Test-Path -LiteralPath $dst) {{
      $bak = Join-Path -Path $backup -ChildPath $f
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bak) | Out-Null
      Copy-Item -LiteralPath $dst -Destination $bak -Force
    }}
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
  }}
  foreach ($f in @({deletes_ps})) {{
    Remove-Item -LiteralPath (Join-Path -Path $base -ChildPath $f) -Force -ErrorAction SilentlyContinue
  }}
}} catch {{
  New-Item -ItemType Directory -Force -Path (Join-Path -Path $base -ChildPath 'updates') | Out-Null
  "update failed: $($_.Exception.Message)" | Out-File -LiteralPath (Join-Path -Path $base -ChildPath 'updates\\apply-error.log') -Append -Encoding utf8
}}
Start-Process -FilePath (Join-Path -Path $base -ChildPath 'PTTAutoPost.exe') -WorkingDirectory $base
Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
    script.write_text("\ufeff" + body, encoding="utf-8")
    # CREATE_NO_WINDOW works for powershell.exe; DETACHED_PROCESS makes it exit without running the script.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", str(script)], creationflags=flags, close_fds=True)
    log.info("delta update staged: %s files, backup %s", len(staged.files), backup)
    return script


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
