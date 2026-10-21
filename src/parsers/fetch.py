"""Polite, bounded page fetching. Never logs in, never uses cookies, never works around walls."""
from __future__ import annotations

import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

from ..errors import FetchError, InputError
from ..logging_setup import get_logger

log = get_logger("fetch")
USER_AGENT = "PTTAutoPost/0.1 (personal desktop tool; single GET per article; honest UA)"
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 15
MAX_REDIRECTS = 5
_RESTRICTED = {401: "需要登入", 402: "需要付費", 403: "存取被拒（可能是登入牆、付費牆或反爬機制）", 451: "因法律原因無法存取"}
_robots_cache: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str]] = {}
_last_hit: dict[str, float] = {}


@dataclass
class Fetched:
    url: str
    final_url: str
    status: int
    content_type: str
    charset: str
    html: str
    size: int
    warnings: list[str] = field(default_factory=list)


def validate_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise InputError("請輸入網址。")
    if any(c in url for c in " \r\n\t"):
        raise InputError("網址不可含空白或換行。")
    try:
        p = urlparse(url)
        host = p.hostname
    except ValueError as e:
        raise InputError("網址格式錯誤。", str(e)) from e
    if p.scheme not in ("http", "https"):
        raise InputError(f"不支援的網址類型「{p.scheme or '無'}」，僅支援 http／https。")
    if not host:
        raise InputError("網址缺少主機名稱。")
    return url


def _robots(url: str, timeout: float) -> tuple[bool | None, str, float | None]:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots_cache:
        rp, note = None, ""
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=min(timeout, 6))
            if r.status_code == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(r.content.decode("utf-8-sig", "replace").splitlines())
            elif r.status_code >= 500:
                note = f"無法確認 robots.txt（HTTP {r.status_code}）"
        except requests.RequestException:
            note = "無法讀取 robots.txt"
        _robots_cache[base] = (rp, note)
    rp, note = _robots_cache[base]
    if rp is None:
        return None, note, None
    return rp.can_fetch(USER_AGENT, url), note, rp.crawl_delay(USER_AGENT)


def _decode(raw: bytes, header_charset: str | None, warnings: list[str]) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace"), "utf-8"
    cands = []
    if header_charset:
        cands.append(header_charset)
    m = re.search(rb"<meta[^>]+charset=[\"']?\s*([A-Za-z0-9_\-]+)", raw[:8192], re.I)
    if m:
        cands.append(m.group(1).decode("ascii", "ignore"))
    for cs in cands:
        try:
            return raw.decode(cs), cs.lower()
        except (LookupError, UnicodeDecodeError):
            continue
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None:
            warnings.append(f"網頁未宣告編碼，已自動偵測為 {best.encoding}（請確認文字無亂碼）。")
            return str(best), best.encoding
    except Exception:  # noqa: BLE001
        pass
    warnings.append("編碼無法判定，以 UTF-8 解碼（可能有亂碼）。")
    return raw.decode("utf-8", "replace"), "utf-8?"


def fetch(raw_url: str, timeout: float = TIMEOUT, max_bytes: int = MAX_BYTES,
          ignore_robots: bool = False, min_interval: float = 2.0) -> Fetched:
    url = validate_url(raw_url)
    warnings: list[str] = []
    allowed, note, delay = _robots(url, timeout)
    if note:
        warnings.append(note)
    if allowed is False and not ignore_robots:
        raise FetchError("該網站的 robots.txt 不允許擷取此路徑（可勾選「忽略 robots」由您自行承擔後再試）。", "robots")
    host = urlparse(url).netloc
    wait = max(min_interval, delay or 0) - (time.monotonic() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(min(wait, 12))
    _last_hit[host] = time.monotonic()
    sess = requests.Session()
    sess.max_redirects = MAX_REDIRECTS
    sess.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                         "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.5"})
    try:
        r = sess.get(url, timeout=timeout, stream=True, allow_redirects=True)
    except requests.exceptions.TooManyRedirects as e:
        raise FetchError("重新導向次數過多。", str(e)) from e
    except requests.exceptions.Timeout as e:
        raise FetchError(f"連線逾時（{int(timeout)} 秒）。", str(e)) from e
    except requests.exceptions.SSLError as e:
        raise FetchError("SSL 憑證驗證失敗。", str(e)) from e
    except requests.RequestException as e:
        raise FetchError("無法連線到網站。", str(e)) from e
    try:
        final = r.url
        if urlparse(final).scheme not in ("http", "https"):
            raise FetchError("網站導向到不支援的網址類型。", final)
        if r.status_code in _RESTRICTED:
            raise FetchError(f"HTTP {r.status_code}：{_RESTRICTED[r.status_code]}。程式不會嘗試繞過限制。", "restricted")
        if r.status_code >= 400:
            raise FetchError(f"網站回應錯誤 HTTP {r.status_code}。", "http")
        ctype = r.headers.get("Content-Type", "")
        if not re.search(r"html|xml", ctype, re.I):
            raise FetchError(f"內容類型不是網頁（{ctype or '未知'}）。", "type")
        chunks, total = [], 0
        for c in r.iter_content(65536):
            total += len(c)
            if total > max_bytes:
                raise FetchError(f"網頁超過大小上限（{max_bytes // 1024 // 1024} MB）。", "size")
            chunks.append(c)
        raw = b"".join(chunks)
        hc = re.search(r"charset=([\w\-]+)", ctype, re.I)
        text, cs = _decode(raw, hc.group(1) if hc else None, warnings)
        log.info("fetched %s status=%s bytes=%d charset=%s", host, r.status_code, total, cs)
        return Fetched(url, final, r.status_code, ctype, cs, text, total, warnings)
    finally:
        r.close()
