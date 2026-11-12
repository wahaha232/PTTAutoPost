"""Recently connected BBS endpoints (addresses only, never accounts or passwords)."""
from __future__ import annotations

import json

from .net.client import endpoint_problem

SETTING_KEY = "connect.history"
MAX_ENTRIES = 10


def _clean(urls) -> list[str]:
    out: list[str] = []
    for u in urls if isinstance(urls, list) else []:
        if isinstance(u, str) and u.strip() and endpoint_problem(u.strip()) is None and u.strip() not in out:
            out.append(u.strip())
    return out[:MAX_ENTRIES]


def parse(raw: str) -> list[str]:
    """Stored JSON -> list; anything malformed or no longer allowed is dropped instead of raising."""
    try:
        return _clean(json.loads(raw or "[]"))
    except (ValueError, TypeError):
        return []


def dump(urls: list[str]) -> str:
    return json.dumps(_clean(urls), ensure_ascii=False)


def add(urls: list[str], url: str) -> list[str]:
    """Move url to the front (most recent first), keep at most MAX_ENTRIES; refused endpoints are not recorded."""
    url = (url or "").strip()
    if not url or endpoint_problem(url) is not None:
        return _clean(urls)
    return _clean([url] + [u for u in urls if u != url])
