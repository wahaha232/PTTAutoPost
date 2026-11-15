"""Read PTT's article viewer (pmore) state from the emulated screen.

Footer formats come from pttbbs mbbsd/pmore.c:
    "  瀏覽 第 %1d/%1d 頁 (%3d%%) " + " 目前顯示: 第 %02d~%02d 行"   (pmore footer)
    "  瀏覽 第 %1d 頁 (%3d%%) "                                        (page count unknown)
    "  瀏覽 P.%d(%d%%)  "                                              (old status bar option)
In pmore, KEY_DOWN at the end of an article (100%) quits to the next article, so the mouse
wheel must stop there instead of sending another arrow.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .screen import WIDE2, Screen

_PROGRESS = re.compile(r"瀏覽\s*(?:第\s*\d+(?:\s*/\s*\d+)?\s*頁|P\.\d+)\s*\(\s*(\d{1,3})%\)")
_LINES = re.compile(r"(?:目前顯示:\s*第|顯示範圍:.*?,)\s*(\d+)~(\d+)\s*行")
# push / boo / arrow comment: "推 userid: text" (pttbbs pads the id, so allow spaces before ':')
_PUSH = re.compile(r"^(推|噓|→) ([A-Za-z][A-Za-z0-9]{1,15})\s*:")


@dataclass(frozen=True)
class Reading:
    progress: int
    first_line: int | None          # None with the old status bar (no line numbers)

    @property
    def at_end(self) -> bool:
        return self.progress >= 100

    @property
    def at_top(self) -> bool:
        return self.first_line == 1


def reading_state(s: Screen) -> Reading | None:
    """The pmore footer on the last row, or None when no article is being read."""
    footer = s.row_text(s.rows - 1)
    m = _PROGRESS.search(footer)
    if not m:
        return None
    lines = _LINES.search(footer)
    return Reading(int(m.group(1)), int(lines.group(1)) if lines else None)


def _row_cells(s: Screen, y: int) -> tuple[str, list[int]]:
    """Row text plus the screen column where each character starts."""
    chars, cols = [], []
    for x, cell in enumerate(s.grid[y]):
        if cell[3] & WIDE2:
            continue
        chars.append(cell[0])
        cols.append(x)
    return "".join(chars), cols


def merged_push_rows(s: Screen) -> dict[int, int]:
    """Rows whose push comes from the same id as the row above -> number of prefix cells to hide.

    Only consecutive comment rows are merged; the footer row is never touched.  The screen text is
    unchanged (copy still gets the full lines); this only drives how the rows are painted.
    """
    out: dict[int, int] = {}
    prev_id = None
    for y in range(s.rows - 1):
        text, cols = _row_cells(s, y)
        m = _PUSH.match(text)
        if not m:
            prev_id = None
            continue
        uid = m.group(2).lower()
        if uid == prev_id:
            end = m.end()                                   # index just after ':'
            out[y] = cols[end] if end < len(cols) else (cols[-1] + 1)
        prev_id = uid
    return out
