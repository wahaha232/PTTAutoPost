"""Fetch an image link for the in-app viewer (never a browser, never a shell).

The same per-hop rules as the article fetcher apply: https only, no credentials,
a resolved public address pinned for every hop, bounded redirects and bytes, and
image content types only (SVG is refused).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from urllib.parse import urljoin

import requests

from ..errors import FetchError
from ..links import is_auto_open_image_url
from ..logging_setup import get_logger
from ..parsers.fetch import (MAX_REDIRECTS, USER_AGENT, _mount_pinning, _pin_session,  # shared SSRF/DNS-pinning rules
                             validate_url)

log = get_logger("image")
TIMEOUT = 15
MAX_IMAGE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class ImageData:
    url: str
    content_type: str
    data: bytes


def check_hop(url: str) -> str:
    """Allow only https URLs on a known image host, including every redirect target."""
    if not is_auto_open_image_url(url):
        raise FetchError("只會在主程式內開啟已知圖床的 https 圖片連結。", "url")
    return validate_url(url)


def _content_type(headers) -> str:
    return (headers.get("Content-Type") or "").split(";")[0].strip().lower()


def fetch_image(raw_url: str, timeout: float = TIMEOUT, max_bytes: int = MAX_IMAGE_BYTES,
                cancel: threading.Event | None = None) -> ImageData:
    """Download one image into memory; never writes a file, never follows a redirect off the image policy."""
    url = check_hop(raw_url)
    cur, hops = url, 0
    with requests.Session() as sess:                          # releases the urllib3 pool even on errors
        _mount_pinning(sess)
        sess.headers.update({"User-Agent": USER_AGENT, "Accept": "image/jpeg,image/png,image/gif,image/webp,image/bmp"})
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
                cur = check_hop(urljoin(cur, loc))             # same https / known-host policy for every hop
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
