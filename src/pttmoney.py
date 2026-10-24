"""PTT P-coin estimates for article text (based on PTT's published rule).

Rule: each valid typed character gives 0.25 P, but at most 1 P per 2 seconds;
a normal article is capped at 1000 P, a news-category title at 25 P.  These are
estimates only: PTT remains authoritative.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

POINTS_PER_CHAR = 0.25
MAX_POINTS_PER_TWO_SECONDS = 1.0
NORMAL_CAP = 1000
NEWS_CAP = 25
NEWS_PREFIX = "[新聞]"
SECONDS_PER_CHAR_AT_MAX_RATE = 2 / 4          # 4 chars per 2 seconds
FAST_CHUNK_BYTES = 100
FAST_CHUNK_SECONDS = 0.15                     # estimate: server quiet window + echo


@dataclass(frozen=True)
class Estimate:
    chars: int
    cap: int
    points: float
    seconds: float
    capped: bool
    news: bool


def valid_chars(text: str) -> int:
    """Characters PTT is expected to count: printable and not whitespace."""
    return sum(1 for ch in text if not ch.isspace() and ch.isprintable())


def is_news_title(title: str) -> bool:
    return title.strip().startswith(NEWS_PREFIX)


def fast_seconds(text: str) -> float:
    """Rough duration of the normal chunked typer (100-byte chunks, ~0.15 s each)."""
    raw = len((text or "").encode("cp950", errors="replace"))
    chunks = max(1, math.ceil(raw / FAST_CHUNK_BYTES)) + (text or "").count("\n")
    return chunks * FAST_CHUNK_SECONDS


def estimate(title: str, body: str, mode: str = "money") -> Estimate:
    """mode='money' paces 4 chars per 2 s (maximum P); mode='fast' is the normal typer."""
    chars = valid_chars(body)
    cap = NEWS_CAP if is_news_title(title) else NORMAL_CAP
    raw = chars * POINTS_PER_CHAR
    seconds = fast_seconds(body) if mode == "fast" else chars * SECONDS_PER_CHAR_AT_MAX_RATE
    points = min(cap, raw, seconds * MAX_POINTS_PER_TWO_SECONDS / 2)
    return Estimate(chars=chars, cap=cap, points=round(points, 2), seconds=seconds,
                    capped=raw > cap, news=cap == NEWS_CAP)


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    if total < 1:
        return "不到 1 秒"
    minutes, sec = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} 小時 {minutes} 分"
    if minutes:
        return f"{minutes} 分 {sec} 秒"
    return f"{sec} 秒"
