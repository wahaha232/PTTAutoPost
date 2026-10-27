"""Selection geometry and text extraction for the terminal grid.

Coordinates are grid cells: (row, column). A double-width character occupies two
cells; the second cell carries WIDE2 and an empty string. Any selection boundary
that touches one half is expanded so the whole character is included.
"""
from __future__ import annotations

from .screen import WIDE2

Point = tuple[int, int]


def clamp(point: Point, cols: int, rows: int) -> Point:
    row, col = point
    return max(0, min(rows - 1, row)), max(0, min(cols - 1, col))


def _trail(grid, row: int, col: int) -> bool:
    return bool(grid[row][col][3] & WIDE2)


def _start_col(grid, row: int, col: int) -> int:
    return col - 1 if col > 0 and _trail(grid, row, col) else col


def _end_col(grid, row: int, col: int) -> int:
    last = len(grid[row]) - 1
    if col < last and _trail(grid, row, col + 1):
        return col + 1
    return col


def _text(grid, row: int, start: int, end: int) -> str:
    out = []
    for col in range(start, end + 1):
        char, _fg, _bg, flags = grid[row][col]
        if not flags & WIDE2:
            out.append(char)
    return "".join(out)


def selection_rows(grid, anchor: Point, cursor: Point, rect: bool = False) -> list[tuple[int, int, int]]:
    """Inclusive (row, start_col, end_col) spans for painting and text.

    Linear selection: the first row runs from the anchor to the end of the row,
    middle rows are whole rows, the last row runs from the start to the cursor.
    Rectangular selection keeps the same columns on every row.
    """
    rows, cols = len(grid), len(grid[0])
    anchor, cursor = clamp(anchor, cols, rows), clamp(cursor, cols, rows)
    spans: list[tuple[int, int, int]] = []
    if rect:
        top, bottom = sorted((anchor[0], cursor[0]))
        left, right = sorted((anchor[1], cursor[1]))
        for row in range(top, bottom + 1):
            spans.append((row, _start_col(grid, row, left), _end_col(grid, row, right)))
        return spans
    start, end = sorted((anchor, cursor))
    r0, c0 = start
    r1, c1 = end
    for row in range(r0, r1 + 1):
        if r0 == r1:
            first, last = c0, c1
        elif row == r0:
            first, last = c0, cols - 1
        elif row == r1:
            first, last = 0, c1
        else:
            first, last = 0, cols - 1
        spans.append((row, _start_col(grid, row, first), _end_col(grid, row, last)))
    return spans


def selection_text(grid, anchor: Point, cursor: Point, rect: bool = False) -> str:
    """Selected text with trailing whitespace removed from every line and no trailing blank lines."""
    return "\n".join(_text(grid, row, start, end).rstrip()
                     for row, start, end in selection_rows(grid, anchor, cursor, rect)).rstrip("\n")


def word_span(grid, row: int, col: int) -> tuple[int, int] | None:
    """Inclusive span of the non-whitespace word around a cell, or None on whitespace."""
    cols = len(grid[row])
    col = max(0, min(cols - 1, col))
    col = _start_col(grid, row, col)
    char = grid[row][col][0]
    if not char or char.isspace():
        return None
    left = col
    while left > 0:
        prev = left - 1
        if _trail(grid, row, prev):
            prev = max(0, prev - 1)                   # an orphan trail in column 0 must not wrap to -1
        prev_char = grid[row][prev][0]
        if not prev_char or prev_char.isspace():
            break
        left = prev
    right = col + (2 if col + 1 < cols and _trail(grid, row, col + 1) else 1)
    while right < cols:
        if _trail(grid, row, right):
            right += 1
            continue
        char = grid[row][right][0]
        if not char or char.isspace():
            break
        right += 2 if right + 1 < cols and _trail(grid, row, right + 1) else 1
    return left, right - 1


def screen_text(grid) -> str:
    """Whole screen as text: trailing whitespace per row, no trailing empty rows."""
    lines = [_text(grid, row, 0, len(grid[row]) - 1).rstrip() for row in range(len(grid))]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)
