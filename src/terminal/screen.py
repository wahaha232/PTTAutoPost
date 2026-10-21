"""Minimal VT100/ANSI screen for PTT (Big5 + ANSI escape sequences, 80x24 by default).

Design notes (all behaviours below are exercised by tests/test_screen.py):
* Bytes are tokenised by hand: a Big5 lead byte followed by ESC/control is NOT swallowed
  (PTT frequently cuts a double-byte char with a colour code).
* Every character decoded from two bytes occupies two cells (PTT/Big5 convention), whatever
  its Unicode East-Asian width is (box/block symbols are ambiguous-width in Unicode).
* Erase operations use the current background colour (PTT status bars rely on that).
* Auto-wrap is deferred (xterm style) so an 80-column line followed by CR LF does not skip a row.
"""
from __future__ import annotations

from dataclasses import dataclass

BOLD, REVERSE, UNDERLINE, BLINK, WIDE2 = 1, 2, 4, 8, 16
DEFAULT_FG, DEFAULT_BG = 7, 0
BLANK = (" ", DEFAULT_FG, DEFAULT_BG, 0)


@dataclass
class Cursor:
    x: int = 0
    y: int = 0


class Screen:
    def __init__(self, cols: int = 80, rows: int = 24):
        self.cols, self.rows = cols, rows
        self.cur = Cursor()
        self.fg, self.bg, self.flags = DEFAULT_FG, DEFAULT_BG, 0
        self._saved = (0, 0)
        self._wrap_pending = False
        self._state = "ground"
        self._csi = bytearray()
        self._lead: int | None = None
        self.grid: list[list[tuple]] = [[BLANK] * cols for _ in range(rows)]
        self.bytes_fed = 0
        self.bell = 0

    # ------------------------------------------------------------------ queries
    def row_text(self, y: int) -> str:
        return "".join(c[0] for c in self.grid[y] if not (c[3] & WIDE2)).rstrip()

    def text(self) -> str:
        return "\n".join(self.row_text(y) for y in range(self.rows))

    def contains(self, needle: str) -> bool:
        return any(needle in self.row_text(y) for y in range(self.rows))

    def last_nonblank_row(self) -> int:
        for y in range(self.rows - 1, -1, -1):
            if self.row_text(y):
                return y
        return -1

    # ------------------------------------------------------------------ feeding
    def feed(self, data: bytes) -> None:
        self.bytes_fed += len(data)
        for b in data:
            self._byte(b)

    def _byte(self, b: int) -> None:
        # PTT often puts a colour escape BETWEEN the two bytes of one Big5 character (lead, ESC[..m, trail).
        # The lead byte therefore stays pending across escape sequences and is completed by the next data byte.
        if self._lead is not None and self._state == "ground" and b != 0x1B:
            lead, self._lead = self._lead, None
            if 0x40 <= b <= 0x7E or 0xA1 <= b <= 0xFE:
                try:
                    ch = bytes((lead, b)).decode("cp950")
                except UnicodeDecodeError:
                    ch = "？"  # keep the 2-cell alignment even for UAO-only characters
                self._put(ch, 2)
                return
            self._put("？", 2)  # truly dangling lead byte (e.g. followed by CR/LF); handle b normally
        st = self._state
        if st == "ground":
            if b == 0x1B:
                self._state = "esc"
            elif b >= 0x80:
                self._lead = b
            elif b >= 0x20 and b != 0x7F:
                self._put(chr(b), 1)
            else:
                self._control(b)
        elif st == "esc":
            if b == 0x5B:  # [
                self._state, self._csi = "csi", bytearray()
            elif b in b"()#%":
                self._state = "esc_skip"
            else:
                self._state = "ground"
                self._esc_simple(b)
        elif st == "esc_skip":
            self._state = "ground"
        elif st == "csi":
            if 0x40 <= b <= 0x7E:
                self._state = "ground"
                self._csi_final(chr(b), bytes(self._csi).decode("ascii", "replace"))
            elif b == 0x1B:  # aborted sequence
                self._state, self._csi = "esc", bytearray()
            elif b < 0x20:
                self._control(b)
            else:
                self._csi.append(b)

    # ------------------------------------------------------------------ primitives
    def _control(self, b: int) -> None:
        if b == 0x0D:
            self.cur.x, self._wrap_pending = 0, False
        elif b in (0x0A, 0x0B, 0x0C):
            self._linefeed()
        elif b == 0x08:
            self.cur.x, self._wrap_pending = max(0, self.cur.x - 1), False
        elif b == 0x09:
            self.cur.x = min(self.cols - 1, (self.cur.x // 8 + 1) * 8)
        elif b == 0x07:
            self.bell += 1

    def _esc_simple(self, b: int) -> None:
        c = chr(b)
        if c == "7":
            self._saved = (self.cur.x, self.cur.y)
        elif c == "8":
            self.cur.x, self.cur.y = self._saved
        elif c == "M":
            if self.cur.y == 0:
                self._scroll_down(1)
            else:
                self.cur.y -= 1
        elif c == "D":
            self._linefeed()
        elif c == "E":
            self.cur.x = 0
            self._linefeed()
        elif c == "c":
            self.__init__(self.cols, self.rows)

    def _linefeed(self) -> None:
        self._wrap_pending = False
        if self.cur.y >= self.rows - 1:
            self._scroll_up(1)
        else:
            self.cur.y += 1

    def _scroll_up(self, n: int) -> None:
        for _ in range(n):
            self.grid.pop(0)
            self.grid.append([(" ", DEFAULT_FG, self.bg, 0)] * self.cols)

    def _scroll_down(self, n: int) -> None:
        for _ in range(n):
            self.grid.pop()
            self.grid.insert(0, [(" ", DEFAULT_FG, self.bg, 0)] * self.cols)

    def _attr(self, extra: int = 0) -> tuple[int, int, int]:
        return self.fg, self.bg, self.flags | extra

    def _put(self, ch: str, width: int) -> None:
        if self._wrap_pending or self.cur.x + width > self.cols:
            self.cur.x, self._wrap_pending = 0, False
            self._linefeed()
        row = self.grid[self.cur.y]
        x = self.cur.x
        # overwriting half of a wide char blanks its partner
        if row[x][3] & WIDE2 and x > 0:
            row[x - 1] = (" ",) + row[x - 1][1:]
        fg, bg, fl = self._attr()
        row[x] = (ch, fg, bg, fl)
        if width == 2:
            row[x + 1] = ("", fg, bg, fl | WIDE2)
            if x + 2 < self.cols and row[x + 2][3] & WIDE2:
                row[x + 2] = (" ",) + row[x + 2][1:3] + (0,)
        elif x + 1 < self.cols and row[x + 1][3] & WIDE2:
            row[x + 1] = (" ",) + row[x + 1][1:3] + (0,)
        nx = x + width
        if nx >= self.cols:
            self.cur.x, self._wrap_pending = self.cols - 1, True
        else:
            self.cur.x = nx

    # ------------------------------------------------------------------ CSI
    def _csi_final(self, f: str, raw: str) -> None:
        if raw.startswith(("?", ">", "=", "!")):
            return  # private modes (cursor visibility etc.) are ignored
        try:
            p = [int(x) if x else 0 for x in raw.split(";")] if raw else []
        except ValueError:
            return

        def a(i: int, d: int) -> int:
            return p[i] if len(p) > i and p[i] > 0 else d

        c = self.cur
        self._wrap_pending = False if f in "ABCDEFGHfdJKLMP@X" else self._wrap_pending
        if f == "A":
            c.y = max(0, c.y - a(0, 1))
        elif f == "B":
            c.y = min(self.rows - 1, c.y + a(0, 1))
        elif f == "C":
            c.x = min(self.cols - 1, c.x + a(0, 1))
        elif f == "D":
            c.x = max(0, c.x - a(0, 1))
        elif f == "E":
            c.x, c.y = 0, min(self.rows - 1, c.y + a(0, 1))
        elif f == "F":
            c.x, c.y = 0, max(0, c.y - a(0, 1))
        elif f == "G":
            c.x = min(self.cols - 1, a(0, 1) - 1)
        elif f in "Hf":
            c.y, c.x = min(self.rows - 1, a(0, 1) - 1), min(self.cols - 1, a(1, 1) - 1)
        elif f == "d":
            c.y = min(self.rows - 1, a(0, 1) - 1)
        elif f == "J":
            self._erase_display(p[0] if p else 0)
        elif f == "K":
            self._erase_line(p[0] if p else 0)
        elif f == "L":
            for _ in range(a(0, 1)):
                self.grid.pop()
                self.grid.insert(c.y, [(" ", DEFAULT_FG, self.bg, 0)] * self.cols)
        elif f == "M":
            for _ in range(a(0, 1)):
                self.grid.pop(c.y)
                self.grid.append([(" ", DEFAULT_FG, self.bg, 0)] * self.cols)
        elif f == "P":
            row = self.grid[c.y]
            n = min(a(0, 1), self.cols - c.x)
            del row[c.x:c.x + n]
            row.extend([(" ", DEFAULT_FG, self.bg, 0)] * n)
        elif f == "@":
            row = self.grid[c.y]
            n = min(a(0, 1), self.cols - c.x)
            row[c.x:c.x] = [(" ", DEFAULT_FG, self.bg, 0)] * n
            del row[self.cols:]
        elif f == "X":
            row = self.grid[c.y]
            for i in range(c.x, min(self.cols, c.x + a(0, 1))):
                row[i] = (" ", DEFAULT_FG, self.bg, 0)
        elif f == "m":
            self._sgr(p or [0])
        elif f == "s":
            self._saved = (c.x, c.y)
        elif f == "u":
            c.x, c.y = self._saved
        # r (scroll region), h/l (modes), n (reports), etc. are intentionally ignored

    def _erase_line(self, mode: int) -> None:
        row, x = self.grid[self.cur.y], self.cur.x
        rng = range(x, self.cols) if mode == 0 else range(0, x + 1) if mode == 1 else range(self.cols)
        for i in rng:
            row[i] = (" ", DEFAULT_FG, self.bg, 0)

    def _erase_display(self, mode: int) -> None:
        y = self.cur.y
        if mode == 0:
            self._erase_line(0)
            rows = range(y + 1, self.rows)
        elif mode == 1:
            self._erase_line(1)
            rows = range(0, y)
        else:
            rows = range(self.rows)
        for r in rows:
            self.grid[r] = [(" ", DEFAULT_FG, self.bg, 0)] * self.cols

    def _sgr(self, params: list[int]) -> None:
        it = iter(params)
        for v in it:
            if v in (38, 48):                              # extended colour (256 / truecolor): not supported, skip its arguments
                mode = next(it, None)
                for _ in range(1 if mode == 5 else 3 if mode == 2 else 0):
                    next(it, None)
                continue
            if v == 0:
                self.fg, self.bg, self.flags = DEFAULT_FG, DEFAULT_BG, 0
            elif v == 1:
                self.flags |= BOLD
            elif v == 4:
                self.flags |= UNDERLINE
            elif v == 5:
                self.flags |= BLINK
            elif v == 7:
                self.flags |= REVERSE
            elif v == 22:
                self.flags &= ~BOLD
            elif v == 24:
                self.flags &= ~UNDERLINE
            elif v == 25:
                self.flags &= ~BLINK
            elif v == 27:
                self.flags &= ~REVERSE
            elif 30 <= v <= 37:
                self.fg = v - 30
            elif v == 39:
                self.fg = DEFAULT_FG
            elif 40 <= v <= 47:
                self.bg = v - 40
            elif v == 49:
                self.bg = DEFAULT_BG
            elif 90 <= v <= 97:
                self.fg, self.flags = v - 90, self.flags | BOLD
