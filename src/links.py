"""Detect http/https URLs on an emulated PTT screen.

Only a single screen row is considered: a URL wrapped by the terminal is not joined or guessed.  Cell ranges are
kept in screen columns so the UI can underline/hit-test Chinese double-width text correctly.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

from .terminal.screen import WIDE2

_URL_RE = re.compile(r"(?i)(?<![A-Za-z0-9])https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
_TRAILING = ".,;:!?，。；：！？、\"'」』】》〉)]}"
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
_IMAGE_HOSTS = (
    "imgur.com", "i.imgur.com", "m.imgur.com", "imgbox.com", "i.ibb.co", "ibb.co",
    "gyazo.com", "puu.sh", "flic.kr", "postimg.cc", "i.postimg.cc", "imageshack.us",
)


@dataclass(frozen=True)
class Link:
    url: str
    row: int
    start_col: int
    end_col: int                 # exclusive

    def contains(self, row: int, col: int) -> bool:
        return row == self.row and self.start_col <= col < self.end_col


def validate_http_url(url: str) -> bool:
    """Only plain http/https URLs with a host and no credentials are allowed."""
    if not url or any(ord(c) < 32 or ord(c) == 127 or c.isspace() for c in url):
        return False
    try:
        p = urlparse(url)
        host = p.hostname
    except ValueError:
        return False
    if p.scheme.lower() not in ("http", "https") or not host:
        return False
    if p.username or p.password:
        return False
    return True


def _trim(url: str) -> str:
    """Drop trailing punctuation; a ")" only when it has no matching "(" in the URL (keeps Foo_(bar))."""
    while url and url[-1] in _TRAILING:
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        url = url[:-1]
    return url


def _known_image_host(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in _IMAGE_HOSTS)


def _private_host(host: str) -> bool:
    """String-only check; never performs DNS resolution."""
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def is_image_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        return False
    if _known_image_host(host):
        return True
    return PurePosixPath(p.path).suffix.lower() in _IMAGE_EXTENSIONS


def is_auto_open_image_url(url: str) -> bool:
    """Auto-open https image links on a known image host or with a known image extension."""
    if not validate_http_url(url):
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme.lower() != "https":
        return False
    host = (p.hostname or "").lower().rstrip(".")
    if not host or _private_host(host):
        return False
    suffix = PurePosixPath(p.path).suffix.lower()
    if suffix == ".svg":
        return False
    return _known_image_host(host) or suffix in _IMAGE_EXTENSIONS


def is_article_image_url(url: str) -> bool:
    """An https image URL taken from the article itself (any public host, still no SVG)."""
    if not validate_http_url(url):
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme.lower() != "https":
        return False
    host = (p.hostname or "").lower().rstrip(".")
    if not host or _private_host(host):
        return False
    return PurePosixPath(p.path).suffix.lower() != ".svg"



def _row_cells(screen, y: int) -> tuple[str, list[tuple[int, int]]]:
    """(text, [(start_col, width), ...]) with one entry per visible character."""
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    row = screen.grid[y]
    for x, cell in enumerate(row):
        if cell[3] & WIDE2:       # trailing half of a double-width character
            continue
        width = 2 if x + 1 < len(row) and row[x + 1][3] & WIDE2 else 1
        chars.append(cell[0])
        spans.append((x, width))
    return "".join(chars), spans


def find_links(screen) -> list[Link]:
    """Return links visible on single rows; wrapped URLs are deliberately not joined."""
    found: list[Link] = []
    for y in range(screen.rows):
        text, spans = _row_cells(screen, y)
        for m in _URL_RE.finditer(text):
            url = _trim(m.group(0))
            if not validate_http_url(url):
                continue
            start = spans[m.start()][0]
            end_x, end_w = spans[m.start() + len(url) - 1]
            found.append(Link(url=url, row=y, start_col=start, end_col=end_x + end_w))
    return found


_URL_RUN = re.compile(r"(?i)[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")


def find_image_urls(screen, limit: int = 16) -> list[str]:
    """Image URLs visible on a PTT screen, joining a URL that terminal wrapping split across rows.

    Only https image links (known image hosts or an image suffix) are returned; this is display-only,
    so the result has no row/column spans.
    """
    rows = [_row_cells(screen, y)[0].rstrip() for y in range(screen.rows)]
    found: list[str] = []

    def has_extension(url: str) -> bool:
        return PurePosixPath(urlparse(url).path).suffix.lower() in _IMAGE_EXTENSIONS

    def add(url: str) -> None:
        url = _trim(url)
        if url and url not in found and is_auto_open_image_url(url) and len(found) < limit:
            found.append(url)

    for y, text in enumerate(rows):
        if not text:
            continue
        for m in _URL_RE.finditer(text):
            base = _trim(m.group(0))
            # Only a URL that fills the whole 80-column row can have been split by wrapping;
            # a URL ending a shorter line is complete.
            if m.end() != len(text) or len(text) < screen.cols:
                add(base)
                continue
            if has_extension(base) and is_auto_open_image_url(base):
                add(base)                         # a complete image URL that happens to end at the edge
                continue
            parts = [m.group(0)]
            best = ""
            continued = False
            for yy in range(y + 1, min(y + 4, len(rows))):
                nxt = rows[yy]
                run = _URL_RUN.match(nxt) if nxt and not nxt[0].isspace() else None
                if run is None:
                    break
                continued = True
                parts.append(run.group(0))
                joined = _trim("".join(parts))
                if has_extension(joined) and is_auto_open_image_url(joined):
                    best = joined
                    break
                # Only keep joining when this row is itself full: a short row means the URL
                # ended there and the next line is unrelated text.
                if run.end() < len(nxt) or len(nxt) < screen.cols:
                    break
            add(best or ("" if continued else base))
    return found
