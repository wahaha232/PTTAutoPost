"""Anonymous image upload to well-known public image hosts (no account, no API key).

Only fixed HTTPS endpoints are used; a redirect is refused so the file cannot be
sent to an unexpected host.  The user must confirm each upload (images become
public on a third-party service).
"""
from __future__ import annotations

import mimetypes
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import requests

from ..errors import FetchError, InputError
from ..logging_setup import get_logger
from ..parsers.fetch import _mount_pinning, _pin_session
from ..version import __version__

log = get_logger("upload")
USER_AGENT = f"PTTAutoPost/{__version__} (+https://github.com/wahaha232/PTTAutoPost)"
MAX_RESPONSE_BYTES = 8192
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
MB = 1024 * 1024


@dataclass(frozen=True)
class Host:
    key: str
    label: str
    endpoint: str
    field: str
    extra: dict[str, str]
    max_bytes: int
    allowed_hosts: tuple[str, ...]
    retention: str


HOSTS: dict[str, Host] = {
    "catbox": Host(
        key="catbox", label="Catbox（永久）", endpoint="https://catbox.moe/user/api.php",
        field="fileToUpload", extra={"reqtype": "fileupload", "userhash": ""},
        max_bytes=200 * MB, allowed_hosts=("files.catbox.moe",), retention="永久（圖床政策可能變動）"),
    "litterbox": Host(
        key="litterbox", label="Litterbox（72 小時）",
        endpoint="https://litterbox.catbox.moe/resources/internals/api.php",
        field="fileToUpload", extra={"reqtype": "fileupload", "time": "72h"},
        max_bytes=1024 * MB, allowed_hosts=("litter.catbox.moe",), retention="72 小時後自動刪除"),
    "uguu": Host(
        key="uguu", label="uguu（3 小時）", endpoint="https://uguu.se/upload?output=text",
        field="files[]", extra={}, max_bytes=128 * MB, allowed_hosts=("uguu.se",),
        retention="約 3 小時後自動刪除"),
}


@dataclass(frozen=True)
class UploadResult:
    name: str
    url: str
    host: str
    size: int


@dataclass
class UploadBatch:
    results: list[UploadResult] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


def host_choices() -> list[tuple[str, str]]:
    return [(key, f"{host.label}・單檔 ≤ {host.max_bytes // MB} MB・{host.retention}")
            for key, host in HOSTS.items()]


class _CancellableReader:
    """File wrapper that aborts a large multipart upload as soon as the task is cancelled."""

    def __init__(self, fh, cancel: threading.Event | None = None):
        self._fh = fh
        self._cancel = cancel

    def read(self, size: int = -1) -> bytes:
        if self._cancel is not None and self._cancel.is_set():
            raise FetchError("已取消圖片上傳。", "cancelled")
        return self._fh.read(size)

    def __getattr__(self, name):
        return getattr(self._fh, name)


def _session_for(url: str) -> requests.Session:
    """Session with the same DNS pinning / public-host check as article and image fetches."""
    sess = requests.Session()
    try:
        _mount_pinning(sess)
        _pin_session(sess, url)
    except Exception:
        sess.close()
        raise
    return sess


def _validate_url(url: str, allowed: tuple[str, ...]) -> str:
    try:
        p = urlparse(url)
    except ValueError:
        raise FetchError("圖床回傳的網址無法解析。", url) from None
    host = (p.hostname or "").lower().rstrip(".")
    if p.scheme != "https" or not host or p.username or p.password:
        raise FetchError("圖床回傳的網址不是安全的 https 網址。", url)
    if not any(host == h or host.endswith("." + h) for h in allowed):
        raise FetchError("圖床回傳了非預期的網址，已停止。", url)
    if not p.path or p.path == "/":
        raise FetchError("圖床回傳的網址沒有檔案路徑。", url)
    return url


def upload_image(path: str | Path, host_key: str, timeout: float = 180,
                 cancel: threading.Event | None = None) -> UploadResult:
    host = HOSTS.get(host_key)
    if host is None:
        raise InputError("不支援的圖床。", str(host_key))
    file = Path(path)
    if not file.is_file():
        raise InputError("找不到圖片檔。", str(file))
    if file.suffix.lower() not in IMAGE_EXTS:
        raise InputError("只支援 jpg／jpeg／png／gif／webp／bmp／avif。", file.suffix)
    size = file.stat().st_size
    if size <= 0:
        raise InputError("圖片檔是空的。", str(file))
    if size > host.max_bytes:
        raise InputError(f"{host.label} 單檔上限是 {host.max_bytes // MB} MB。", f"{size} bytes")
    if cancel is not None and cancel.is_set():
        raise FetchError("已取消圖片上傳。", "cancelled")
    ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    headers = {"User-Agent": USER_AGENT, "Accept": "text/plain, */*;q=0.5"}
    try:
        with _session_for(host.endpoint) as sess, file.open("rb") as fh:
            resp = sess.post(host.endpoint, data=host.extra,
                             files={host.field: (file.name, _CancellableReader(fh, cancel), ctype)},
                             headers=headers, timeout=timeout, allow_redirects=False, stream=True)
            try:                                       # read while the session (and its pool) is still open
                if resp.status_code != 200:
                    if resp.status_code == 413:
                        raise FetchError(f"圖床拒絕：檔案超過 {host.max_bytes // MB} MB 上限。", "HTTP 413")
                    if resp.status_code == 429:
                        raise FetchError("圖床忙碌或請求過多，請稍後再試。", "HTTP 429")
                    raise FetchError(f"圖床回應錯誤（HTTP {resp.status_code}）。", _body_hint(resp))
                raw = read_capped(resp, MAX_RESPONSE_BYTES)[0].strip()
            finally:
                resp.close()
    except requests.exceptions.SSLError as e:
        raise FetchError("上傳時 SSL 憑證驗證失敗。", str(e)) from e
    except requests.RequestException as e:
        raise FetchError("無法連線到圖床。", str(e)) from e
    url = raw.splitlines()[0].strip() if raw else ""
    if not url:
        raise FetchError("圖床沒有回傳網址（可能被防火牆或圖床政策阻擋）。", host.endpoint)
    url = _validate_url(url, host.allowed_hosts)
    log.info("uploaded %s to %s (%d bytes)", file.name, host.key, size)
    return UploadResult(name=file.name, url=url, host=host.key, size=size)


def read_capped(resp, cap: int) -> tuple[str, bool]:
    """(text of at most `cap` bytes, whether the body was longer) without loading the whole body."""
    chunks, total = [], 0
    for chunk in resp.iter_content(4096):
        chunks.append(chunk)
        total += len(chunk)
        if total > cap:
            break
    data = b"".join(chunks)
    return data[:cap].decode("utf-8", "replace"), len(data) > cap


def _body_hint(resp) -> str:
    try:
        return read_capped(resp, 300)[0].replace("\n", " ")
    except Exception:  # noqa: BLE001
        return ""


def upload_images(paths: list[str], host_key: str, progress=None,
                  cancel: threading.Event | None = None) -> UploadBatch:
    """Upload sequentially; one failure does not stop the rest. Cancellation stops immediately."""
    batch = UploadBatch()
    for index, path in enumerate(paths, 1):
        if cancel is not None and cancel.is_set():
            break
        try:
            result = upload_image(path, host_key, cancel=cancel)
        except FetchError as e:
            if e.detail == "cancelled":
                break
            batch.errors.append((Path(path).name, e.message))
        except InputError as e:
            batch.errors.append((Path(path).name, e.message))
        else:
            batch.results.append(result)
        if progress is not None:
            progress(index, len(paths), Path(path).name)
    return batch
