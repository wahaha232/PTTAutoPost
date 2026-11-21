"""Small HTTP response helpers shared by uploads and the URL shortener."""
from __future__ import annotations


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
