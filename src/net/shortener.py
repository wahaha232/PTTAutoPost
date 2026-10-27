"""Optional URL shorteners. Explicit user action only; never logs the long URL.

Security notes: fixed HTTPS endpoints, public-host DNS pinning, no credentials/API keys,
response must be an http(s) URL on the selected service's host, and the long URL is sent to
a third party that can log it. is.gd/v.gd/TinyURL/CleanURI are therefore opt-in choices.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from ..errors import FetchError, InputError
from ..links import validate_http_url
from ..logging_setup import get_logger
from ..version import __version__
from .upload import _session_for, read_capped

MAX_RESPONSE_BYTES = 4096

log = get_logger("shortener")


@dataclass(frozen=True)
class Service:
    key: str
    label: str
    endpoint: str
    host: str
    method: str = "GET"
    param: str = "url"


SERVICES: dict[str, Service] = {
    "tinyurl": Service("tinyurl", "TinyURL（第三方，短網址通常永久）",
                       "https://tinyurl.com/api-create.php", "tinyurl.com"),
    "isgd": Service("isgd", "is.gd（第三方，可能永久；會看到網址與 IP）",
                    "https://is.gd/create.php", "is.gd"),
    "vgd": Service("vgd", "v.gd（第三方，與 is.gd 同營運者）",
                   "https://v.gd/create.php", "v.gd"),
    "cleanuri": Service("cleanuri", "CleanURI（第三方）",
                        "https://cleanuri.com/api/v1/shorten", "cleanuri.com", "POST"),
}


def choices() -> list[tuple[str, str]]:
    return [(s.key, s.label) for s in SERVICES.values()]


def _allowed_response(url: str, host: str) -> bool:
    if not validate_http_url(url):
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    h = (p.hostname or "").lower().rstrip(".")
    return p.scheme.lower() == "https" and (h == host or h.endswith("." + host))


def shorten_url(service_key: str, url: str, timeout: float = 10,
                cancel: threading.Event | None = None) -> str:
    svc = SERVICES.get(service_key)
    if svc is None:
        raise InputError("不支援的縮網址服務。", str(service_key))
    url = (url or "").strip()
    if not validate_http_url(url):
        raise InputError("原文網址不是有效的 http／https 網址。")
    if len(url) > 4096:
        raise InputError("原文網址過長（上限 4096 字元）。")
    if cancel is not None and cancel.is_set():
        raise FetchError("已取消縮網址。", "cancelled")
    headers = {"User-Agent": f"PTTAutoPost/{__version__}", "Accept": "application/json, text/plain;q=0.8"}
    try:
        with _session_for(svc.endpoint) as sess:
            if svc.method == "POST":
                resp = sess.post(svc.endpoint, json={svc.param: url}, headers=headers,
                                 timeout=timeout, allow_redirects=False, stream=True)
            else:
                resp = sess.get(svc.endpoint, params={svc.param: url}, headers=headers,
                                timeout=timeout, allow_redirects=False, stream=True)
            try:                                      # bounded read while the session is still open
                status = resp.status_code
                text, too_long = read_capped(resp, MAX_RESPONSE_BYTES) if status == 200 else ("", False)
            finally:
                resp.close()
    except requests.exceptions.SSLError as e:
        raise FetchError("縮網址服務 SSL 憑證驗證失敗。", str(e)) from e
    except requests.RequestException as e:
        raise FetchError("無法連線到縮網址服務。", str(e)) from e
    if cancel is not None and cancel.is_set():
        raise FetchError("已取消縮網址。", "cancelled")
    if status != 200:
        raise FetchError(f"縮網址服務回傳 HTTP {status}。")
    if too_long:
        raise FetchError("縮網址服務回傳的內容過長，已拒絕。")
    if svc.method == "POST":
        try:
            short = str(json.loads(text).get("result_url", "")).strip()
        except (ValueError, AttributeError):
            raise FetchError("縮網址服務回傳的格式不正確。") from None
    else:
        short = text.strip()
    if not _allowed_response(short, svc.host):
        raise FetchError("縮網址服務回傳了非預期的網址，已拒絕。")
    log.info("shortened URL via %s", svc.key)          # never log the URL itself
    return short
