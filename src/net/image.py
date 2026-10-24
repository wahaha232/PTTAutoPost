"""Fetch an image link for the in-app viewer (never a browser, never a shell).

The same per-hop rules as the article fetcher apply: https only, no credentials,
a resolved public address pinned for every hop, bounded redirects and bytes, and
image content types only (SVG is refused).
"""
from __future__ import annotations

import re
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

import requests

from ..errors import FetchError, ToolError
from ..links import is_article_image_url, is_auto_open_image_url
from ..logging_setup import get_logger
from ..parsers.fetch import (MAX_REDIRECTS, USER_AGENT, _mount_pinning, _pin_session,  # shared SSRF/DNS-pinning rules
                             validate_url)

log = get_logger("image")
TIMEOUT = 15
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_ZIP_BYTES = 300 * 1024 * 1024
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "image/webp": ".webp", "image/bmp": ".bmp", "image/avif": ".avif"}


@dataclass(frozen=True)
class ImageData:
    url: str
    content_type: str
    data: bytes


def check_hop(url: str, strict_host: bool = True) -> str:
    """Allow only https image URLs; terminal/hover links additionally need a known host or extension."""
    allowed = is_auto_open_image_url(url) if strict_host else is_article_image_url(url)
    if not allowed:
        raise FetchError("只會在主程式內開啟安全的 https 圖片連結。", "url")
    return validate_url(url)


def _content_type(headers) -> str:
    return (headers.get("Content-Type") or "").split(";")[0].strip().lower()


def fetch_image(raw_url: str, timeout: float = TIMEOUT, max_bytes: int = MAX_IMAGE_BYTES,
                cancel: threading.Event | None = None, strict_host: bool = True,
                referer: str | None = None) -> ImageData:
    """Download one image into memory; never writes a file, never follows a redirect off the image policy.

    `referer` is the article URL; some image CDNs refuse hot-linking without it.
    """
    url = check_hop(raw_url, strict_host)
    cur, hops = url, 0
    with requests.Session() as sess:                          # releases the urllib3 pool even on errors
        _mount_pinning(sess)
        sess.headers.update({"User-Agent": USER_AGENT, "Accept": "image/jpeg,image/png,image/gif,image/webp,image/bmp"})
        if referer and referer.startswith(("http://", "https://")) and not any(c in referer for c in " \r\n\t"):
            sess.headers["Referer"] = referer
        while True:
            _pin_session(sess, cur)                            # resolve + pin every hop, fail closed on DNS errors
            try:
                r = sess.get(cur, timeout=timeout, stream=True, allow_redirects=False)
            except requests.exceptions.Timeout as e:
                raise FetchError(f"圖片連線逾時（{int(timeout)} 秒）。", str(e)) from e
            except requests.exceptions.SSLError as e:
                raise FetchError("圖片的 SSL 憑證驗證失敗。", str(e)) from e
            except requests.RequestException as e:
                raise FetchError("無法連線到圖床。", str(e)) from e
            loc = r.headers.get("Location") if r.status_code in (301, 302, 303, 307, 308) else None
            if not loc:
                break
            r.close()
            hops += 1
            if hops > MAX_REDIRECTS:
                raise FetchError("圖片重新導向次數過多。", cur)
            try:
                cur = check_hop(urljoin(cur, loc), strict_host)   # same policy for every hop
            except FetchError as e:
                raise FetchError("圖片導向到不允許的網址，已停止。", e.detail or e.message) from e
        try:
            if r.status_code in (401, 402, 403, 451):
                raise FetchError(f"圖床拒絕存取（HTTP {r.status_code}）。", "restricted")
            if r.status_code >= 400:
                raise FetchError(f"圖床回應錯誤 HTTP {r.status_code}。", "http")
            ctype = _content_type(r.headers)
            if not ctype.startswith("image/") or "svg" in ctype:
                raise FetchError(f"內容不是可顯示的圖片格式（{ctype or '未知'}）。", "type")
            chunks, total = [], 0
            try:
                for c in r.iter_content(65536):
                    if cancel is not None and cancel.is_set():
                        raise FetchError("已取消圖片下載。", "cancelled")
                    total += len(c)
                    if total > max_bytes:
                        raise FetchError(f"圖片超過大小上限（{max_bytes // 1024 // 1024} MB）。", "size")
                    chunks.append(c)
            except requests.RequestException as e:             # dropped / undecodable body mid-download
                raise FetchError("讀取圖片時連線中斷或內容無法解碼。", f"{type(e).__name__}: {e}") from e
            if not total:
                raise FetchError("圖片內容是空的。", "empty")
            log.info("fetched image status=%s bytes=%d type=%s", r.status_code, total, ctype)
            return ImageData(cur, ctype, b"".join(chunks))
        finally:
            r.close()


@dataclass(frozen=True)
class ZipResult:
    path: Path
    saved: int
    skipped: int
    total_bytes: int
    errors: list[str]


def _zip_name(url: str, content_type: str, used: set[str]) -> str:
    base = unquote(PurePosixPath(urlparse(url).path).name)
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "image"
    suffix = PurePosixPath(base).suffix.lower()
    if suffix not in _IMAGE_EXTS:
        base += _EXT_BY_TYPE.get(content_type, ".img")
    stem, suffix = base.rsplit(".", 1)
    stem, suffix = (stem or "image"), "." + suffix
    candidate, n = stem + suffix, 2
    while candidate.lower() in used:
        candidate = f"{stem}-{n}{suffix}"
        n += 1
    used.add(candidate.lower())
    return candidate


def download_images_zip(urls: list[str], target: Path, referer: str | None = None,
                        progress=None, cancel: threading.Event | None = None) -> ZipResult:
    """Download every image at its original URL into one ZIP (no resizing, no rewriting)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    used: set[str] = set()
    saved = skipped = total = 0
    errors: list[str] = []
    part.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
            for index, url in enumerate(urls, 1):
                if cancel is not None and cancel.is_set():
                    raise FetchError("已取消圖片下載。", "cancelled")
                try:
                    data = fetch_image(url, strict_host=False, referer=referer, cancel=cancel)
                except ToolError as e:
                    skipped += 1
                    errors.append(f"{url}: {e.message}")
                    log.info("article image skipped %s: %s", url, e.message)
                else:
                    if total + len(data.data) > MAX_ZIP_BYTES:
                        raise FetchError(f"圖片總大小超過上限（{MAX_ZIP_BYTES // 1024 // 1024} MB）。", "size")
                    zf.writestr(_zip_name(url, data.content_type, used), data.data)
                    saved += 1
                    total += len(data.data)
                if progress is not None:
                    progress(index, len(urls))
        if saved == 0:
            raise FetchError("沒有任何圖片可以下載。", "empty")
        part.replace(target)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return ZipResult(target, saved, skipped, total, errors)
