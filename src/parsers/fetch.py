"""Polite, bounded page fetching. Never logs in, never uses cookies, never works around walls."""
from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests

from ..errors import FetchError, InputError
from ..logging_setup import get_logger
from ..version import __version__

log = get_logger("fetch")
USER_AGENT = f"PTTAutoPost/{__version__} (personal desktop tool; single GET per article; honest UA)"
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 15
MAX_REDIRECTS = 5
MAX_ROBOTS_BYTES = 512 * 1024
ALLOW_PRIVATE_HOSTS = False            # tests / explicit override only: refuse loopback, LAN and metadata addresses
_RESTRICTED = {401: "需要登入", 402: "需要付費", 403: "存取被拒（可能是登入牆、付費牆或反爬機制）", 451: "因法律原因無法存取"}
_robots_cache: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str]] = {}
_last_hit: dict[str, float] = {}
_lock = threading.Lock()                # FetchTask runs on pool threads: guard the shared caches


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
    if p.username or p.password:
        raise InputError("網址不可包含帳號或密碼（user:password@ 形式）；請移除後再試。")
    return url


def _check_public_host(url: str) -> None:
    """Refuse URLs whose host resolves to loopback / private / link-local / reserved addresses (also after redirects).
    Unresolvable names are left to the HTTP layer, which fails with a normal connection error."""
    if ALLOW_PRIVATE_HOSTS:
        return
    host = urlparse(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast or addr.is_unspecified:
            raise FetchError("網址指向本機或內網位址，為避免誤觸內部服務，已拒絕。", f"{host} -> {addr}")


def _robots(url: str, timeout: float) -> tuple[bool | None, str, float | None]:
    p = urlparse(url)
    base = f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")          # never userinfo
    with _lock:
        cached = base in _robots_cache
    if not cached:
        rp, note = None, ""
        try:
            sess = requests.Session()
            cur, hops = base + "/robots.txt", 0
            while True:                                           # same per-hop SSRF checks as the article itself
                _check_public_host(cur)
                r = sess.get(cur, headers={"User-Agent": USER_AGENT}, timeout=min(timeout, 6), stream=True, allow_redirects=False)
                loc = r.headers.get("Location") if r.status_code in (301, 302, 303, 307, 308) else None
                if not loc:
                    break
                r.close()
                hops += 1
                if hops > 3:
                    raise ValueError("too many robots.txt redirects")
                cur = urljoin(cur, loc)
                validate_url(cur)
            try:
                if r.status_code == 200:
                    data, total = [], 0
                    for c in r.iter_content(16384):
                        total += len(c)
                        if total > MAX_ROBOTS_BYTES:
                            raise ValueError("robots.txt too large")
                        data.append(c)
                    rp = urllib.robotparser.RobotFileParser()
                    rp.parse(b"".join(data).decode("utf-8-sig", "replace").splitlines())
                elif r.status_code >= 500:
                    note = f"無法確認 robots.txt（HTTP {r.status_code}）"
            finally:
                r.close()
        except (requests.RequestException, ValueError, FetchError, InputError):
            note = "無法讀取 robots.txt"
        with _lock:
            _robots_cache[base] = (rp, note)
    with _lock:
        rp, note = _robots_cache[base]
    if rp is None:
        return None, note, None
    return rp.can_fetch(USER_AGENT, url), note, rp.crawl_delay(USER_AGENT)


def _polite(url: str, timeout: float, ignore_robots: bool, min_interval: float, warnings: list[str], first: bool) -> None:
    """robots.txt + per-host request spacing for one hop (every hop, so redirects to another host obey them too)."""
    delay = None
    if not ignore_robots:
        allowed, note, delay = _robots(url, timeout)
        if note and note not in warnings:
            warnings.append(note)
        if allowed is False:
            where = "該網站" if first else "重新導向後的網站"
            raise FetchError(f"{where}的 robots.txt 不允許擷取此路徑（可勾選「忽略 robots」由您自行承擔後再試）。", "robots")
    pu = urlparse(url)
    host = (pu.hostname or "") + (f":{pu.port}" if pu.port else "")
    with _lock:
        wait = max(min_interval, delay or 0) - (time.monotonic() - _last_hit.get(host, 0))
        _last_hit[host] = time.monotonic() + max(wait, 0)     # reserve our slot so parallel fetches queue up
    if wait > 0:
        time.sleep(min(wait, 12))


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
        log.debug("charset detection failed", exc_info=True)
    warnings.append("編碼無法判定，以 UTF-8 解碼（可能有亂碼）。")
    return raw.decode("utf-8", "replace"), "utf-8?"


def _host_of(url: str) -> str:
    pu = urlparse(url)
    return (pu.hostname or "") + (f":{pu.port}" if pu.port else "")


def fetch(raw_url: str, timeout: float = TIMEOUT, max_bytes: int = MAX_BYTES,
          ignore_robots: bool = False, min_interval: float = 2.0) -> Fetched:
    url = validate_url(raw_url)
    warnings: list[str] = []
    host = _host_of(url)
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                         "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.5"})
    cur, hops = url, 0
    while True:
        _check_public_host(cur)
        _polite(cur, timeout, ignore_robots, min_interval, warnings, first=(hops == 0))
        try:
            r = sess.get(cur, timeout=timeout, stream=True, allow_redirects=False)
        except requests.exceptions.Timeout as e:
            raise FetchError(f"連線逾時（{int(timeout)} 秒）。", str(e)) from e
        except requests.exceptions.SSLError as e:
            raise FetchError("SSL 憑證驗證失敗。", str(e)) from e
        except requests.RequestException as e:
            raise FetchError("無法連線到網站。", str(e)) from e
        loc = r.headers.get("Location") if r.status_code in (301, 302, 303, 307, 308) else None
        if not loc:
            break
        r.close()
        hops += 1
        if hops > MAX_REDIRECTS:
            raise FetchError("重新導向次數過多。", url)
        nxt = urljoin(cur, loc)
        try:
            validate_url(nxt)                                  # scheme / userinfo / whitespace checks on every hop
        except InputError as e:
            raise FetchError("網站導向到不支援或不安全的網址。", e.message) from e
        if _host_of(nxt) != _host_of(cur):
            warnings.append(f"已重新導向到另一個網站：{_host_of(nxt)}")
        cur = nxt
    try:
        final = cur
        if urlparse(final).scheme not in ("http", "https"):
            raise FetchError("網站導向到不支援的網址類型。", final)
        if r.status_code in _RESTRICTED:
            raise FetchError(f"HTTP {r.status_code}：{_RESTRICTED[r.status_code]}。程式不會嘗試繞過限制。", "restricted")
        if r.status_code >= 400:
            raise FetchError(f"網站回應錯誤 HTTP {r.status_code}。", "http")
        ctype = r.headers.get("Content-Type", "")
        if not re.search(r"text/html|application/xhtml\+xml", ctype, re.I):         # not SVG / feeds / arbitrary XML
            raise FetchError(f"內容類型不是網頁（{ctype or '未知'}）。", "type")
        chunks, total = [], 0
        try:
            for c in r.iter_content(65536):
                total += len(c)
                if total > max_bytes:
                    raise FetchError(f"網頁超過大小上限（{max_bytes // 1024 // 1024} MB）。", "size")
                chunks.append(c)
        except requests.RequestException as e:             # connection dropped / bad chunked or compressed body mid-download
            raise FetchError("讀取網頁內容時連線中斷或內容無法解碼。", f"{type(e).__name__}: {e}") from e
        raw = b"".join(chunks)
        hc = re.search(r"charset=([\w\-]+)", ctype, re.I)
        text, cs = _decode(raw, hc.group(1) if hc else None, warnings)
        log.info("fetched %s status=%s bytes=%d charset=%s", host, r.status_code, total, cs)
        return Fetched(url, final, r.status_code, ctype, cs, text, total, warnings)
    finally:
        r.close()
