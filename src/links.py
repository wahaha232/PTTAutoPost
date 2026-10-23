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
    return url.rstrip(_TRAILING)


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
    """Auto-open only https URLs on a known image host; extension-only URLs are never auto-opened."""
    if not validate_http_url(url):
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme.lower() != "https":
        return False
    host = (p.hostname or "").lower().rstrip(".")
    if not host or _private_host(host) or not _known_image_host(host):
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
