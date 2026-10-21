"""Terminal view: paints the emulated PTT screen and turns the user's keystrokes into terminal bytes.

Grid model: 80x24 cells; a double-byte (Chinese / box-drawing) character takes two cells. The cell width is derived
from the font's *Chinese* glyph (half of it), so ASCII keeps an even grid even in proportional fonts; ASCII glyphs
that are wider than a cell are squeezed to fit instead of overlapping.
Two layouts: fixed (cell size from the chosen font size) and fit (the font size is chosen automatically so the whole
80x24 grid fills the widget and follows window resizing, with crisp text -- no bitmap scaling).
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..net.session import PttSession
from ..terminal.screen import BOLD, REVERSE, UNDERLINE, WIDE2

NORMAL = [(0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0), (40, 80, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229)]
BRIGHT = [(127, 127, 127), (255, 60, 60), (60, 255, 60), (255, 255, 60), (100, 120, 255), (255, 60, 255), (60, 255, 255), (255, 255, 255)]
_K = Qt.Key
_SPECIAL = {
    _K.Key_Return: b"\r", _K.Key_Enter: b"\r", _K.Key_Backspace: b"\x08", _K.Key_Tab: b"\t", _K.Key_Escape: b"\x1b",
    _K.Key_Up: b"\x1b[A", _K.Key_Down: b"\x1b[B", _K.Key_Right: b"\x1b[C", _K.Key_Left: b"\x1b[D",
    _K.Key_Home: b"\x1b[1~", _K.Key_Insert: b"\x1b[2~", _K.Key_Delete: b"\x1b[3~", _K.Key_End: b"\x1b[4~",
    _K.Key_PageUp: b"\x1b[5~", _K.Key_PageDown: b"\x1b[6~",
}


def key_to_bytes(key: int, mods, text: str) -> tuple[bytes | None, str | None]:
    """Translate one key press. Returns (bytes, None) | (None, reason-if-refused) | (None, None) when ignored."""
    if key in _SPECIAL:
        return _SPECIAL[key], None
    if mods & Qt.KeyboardModifier.ControlModifier and _K.Key_A <= key <= _K.Key_Z:
        return bytes([key - _K.Key_A + 1]), None
    if text and text.isprintable():
        try:
            return text.encode("cp950"), None
        except UnicodeEncodeError:
            return None, f"字元「{text}」無法以 Big5 輸入到 PTT，已忽略。"
    return None, None


def cell_metrics(font: QFont) -> tuple[float, float]:
    """(cell width, cell height) for a font: width from the Chinese glyph so the grid stays even."""
    fm = QFontMetricsF(font)
    return max(fm.horizontalAdvance("M"), fm.horizontalAdvance("中") / 2.0, 4.0), fm.height() + 2.0


_BOX = {  # char -> (up, down, left, right) line weight: 0 none, 1 light, 2 heavy (double lines are drawn heavy)
    "─": (0, 0, 1, 1), "━": (0, 0, 2, 2), "│": (1, 1, 0, 0), "┃": (2, 2, 0, 0),
    "┌": (0, 1, 0, 1), "┐": (0, 1, 1, 0), "└": (1, 0, 0, 1), "┘": (1, 0, 1, 0),
    "├": (1, 1, 0, 1), "┤": (1, 1, 1, 0), "┬": (0, 1, 1, 1), "┴": (1, 0, 1, 1), "┼": (1, 1, 1, 1),
    "┏": (0, 2, 0, 2), "┓": (0, 2, 2, 0), "┗": (2, 0, 0, 2), "┛": (2, 0, 2, 0),
    "┣": (2, 2, 0, 2), "┫": (2, 2, 2, 0), "┳": (0, 2, 2, 2), "┻": (2, 0, 2, 2), "╋": (2, 2, 2, 2),
    "═": (0, 0, 2, 2), "║": (2, 2, 0, 0), "╔": (0, 2, 0, 2), "╗": (0, 2, 2, 0), "╚": (2, 0, 0, 2), "╝": (2, 0, 2, 0),
    "╠": (2, 2, 0, 2), "╣": (2, 2, 2, 0), "╦": (0, 2, 2, 2), "╩": (2, 0, 2, 2), "╬": (2, 2, 2, 2),
}
# block elements as fractions of the cell: (x0, y0, x1, y1)
_BLOCKS = {"▀": (0, 0, 1, .5), "▐": (.5, 0, 1, 1), "▔": (0, 0, 1, 1 / 8), "▕": (7 / 8, 0, 1, 1),
           "▘": (0, 0, .5, .5), "▝": (.5, 0, 1, .5), "▖": (0, .5, .5, 1), "▗": (.5, .5, 1, 1)}
for _i, _c in enumerate("▁▂▃▄▅▆▇█"):
    _BLOCKS[_c] = (0, 1 - (_i + 1) / 8, 1, 1)
for _i, _c in enumerate("▉▊▋▌▍▎▏"):
    _BLOCKS[_c] = (0, 0, (7 - _i) / 8, 1)
_QUADS = {"▙": ("▘", "▖", "▗"), "▚": ("▘", "▗"), "▛": ("▘", "▝", "▖"), "▜": ("▘", "▝", "▗"), "▟": ("▝", "▖", "▗")}
_SHADE = {"░": 64, "▒": 128, "▓": 192}
_TRI = {"◢": ((1, 0), (1, 1), (0, 1)), "◣": ((0, 0), (1, 1), (0, 1)), "◤": ((0, 0), (1, 0), (0, 1)), "◥": ((0, 0), (1, 0), (1, 1))}


def draw_special(p: QPainter, c: str, r: QRectF, color: QColor) -> bool:
    """Draw block / shade / triangle / box-drawing characters geometrically so ASCII art fills its cells exactly
    (font glyphs leave gaps or differ in size between fonts). Returns False for ordinary characters."""
    def frac(b):
        p.fillRect(QRectF(r.left() + b[0] * r.width(), r.top() + b[1] * r.height(),
                          (b[2] - b[0]) * r.width() + .6, (b[3] - b[1]) * r.height() + .6), color)
    if c in _BLOCKS:
        frac(_BLOCKS[c])
    elif c in _QUADS:
        for q in _QUADS[c]:
            frac(_BLOCKS[q])
    elif c in _SHADE:
        col = QColor(color)
        col.setAlpha(_SHADE[c])
        p.fillRect(r, col)
    elif c in _TRI:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([QPointF(r.left() + x * r.width(), r.top() + y * r.height()) for x, y in _TRI[c]]))
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif c in _BOX:
        up, down, left, right = _BOX[c]
        cx, cy = r.center().x(), r.center().y()
        thin = max(1.0, r.height() / 14)
        for wgt, x1, y1, x2, y2 in ((up, cx, r.top(), cx, cy), (down, cx, cy, cx, r.bottom()),
                                    (left, r.left(), cy, cx, cy), (right, cx, cy, r.right(), cy)):
            if wgt:
                t = thin * (2 if wgt == 2 else 1)
                if x1 == x2:
                    p.fillRect(QRectF(x1 - t / 2, y1 - (t / 2 if wgt and y2 == cy else 0), t, abs(y2 - y1) + t / 2 + .6), color)
                else:
                    p.fillRect(QRectF(x1 - (t / 2 if x2 == cx else 0), y1 - t / 2, abs(x2 - x1) + t / 2 + .6, t), color)
    else:
        return False
    return True


class TerminalWidget(QWidget):
    notice = Signal(str)

    PREFERRED = ("MingLiU", "NSimSun", "Microsoft JhengHei Mono", "Consolas", "Courier New")

    def __init__(self, session: PttSession, parent=None, family: str = "", px: int = 17, fill: bool = False):
        super().__init__(parent)
        self.s = session
        self.fill = fill
        self.cw, self.ch = 9.0, 19.0
        self.sx, self.sy, self.ox, self.oy = 1.0, 1.0, 0.0, 0.0   # glyph stretch and grid offset (fit mode)
        self.locked = False                             # True while an automatic typing / login run owns the keyboard
        self.stretch = False                            # True: distort glyphs so the grid fills the area completely
        self._adv: dict[str, float] = {}
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)           # never grabs focus on its own
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.apply_font(family, px)
        self.set_fill(fill)
        self.s.screenChanged.connect(self.update)

    @classmethod
    def default_family(cls) -> str:
        fams = set(QFontDatabase.families())
        return next((f for f in cls.PREFERRED if f in fams), "monospace")

    # ----------------------------------------------------------------- font / layout
    def _make_font(self, family: str, px: int) -> QFont:
        f = QFont(family or self.default_family())
        f.setPixelSize(max(6, min(96, int(px))))
        f.setFixedPitch(True)
        return f

    def apply_font(self, family: str = "", px: int = 17) -> None:
        """Set the user's font (family + size). In fit mode the size is only the starting point."""
        self.font_ = self._make_font(family, px)           # the user's choice (tests / settings read this)
        self.draw_font = self.font_
        self._relayout()

    def set_fill(self, fill: bool) -> None:
        """Fit mode: the grid fills the widget and the font size follows the window size."""
        self.fill = fill
        if fill:
            self.setMinimumSize(240, 144)
            self.setMaximumSize(16777215, 16777215)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._relayout()

    def set_stretch(self, on: bool) -> None:
        self.stretch = bool(on)
        self._relayout()

    def _relayout(self) -> None:
        cols, rows = self.s.screen.cols, self.s.screen.rows
        if self.fill:
            self._fit(max(1, self.width()), max(1, self.height()))
        else:
            self.draw_font = self.font_
            self.cw, self.ch = cell_metrics(self.font_)
            self.sx, self.sy, self.ox, self.oy = 1.0, 1.0, 0.0, 0.0
            self._adv.clear()
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.setFixedSize(self.base_size())
        self.updateGeometry()
        self.update()
        _ = cols, rows

    MAX_STRETCH = 1.25

    def _fit(self, w: int, h: int) -> None:
        """Largest font whose cell fits W/cols x H/rows. The glyph aspect is kept (stretched at most MAX_STRETCH wide,
        and cells at most 1.25x taller than the font); any remaining space becomes an even black margin, so characters
        never end up spread far apart on wide windows."""
        cols, rows = self.s.screen.cols, self.s.screen.rows
        tw, th = w / cols, h / rows
        best = 6
        for px in range(6, 97):
            cw, ch = cell_metrics(self._make_font(self.font_.family(), px))
            if cw <= tw and ch <= th:
                best = px
            else:
                break
        self.draw_font = self._make_font(self.font_.family(), best)
        cwf, chf = cell_metrics(self.draw_font)
        if self.stretch:                                   # fill every pixel: distort the glyphs to the cell
            self.sx, self.sy = tw / cwf, th / chf
            self.cw, self.ch = tw, th
        else:
            self.sx, self.sy = max(1.0, min(tw / cwf, self.MAX_STRETCH)), 1.0
            self.cw = cwf * self.sx
            self.ch = min(th, chf * 1.25)
        self.ox = max(0.0, (w - self.cw * cols) / 2)
        self.oy = max(0.0, (h - self.ch * rows) / 2)
        self._adv.clear()

    def resizeEvent(self, e):
        if self.fill:
            self._fit(max(1, self.width()), max(1, self.height()))
        super().resizeEvent(e)

    def base_size(self) -> QSize:
        cw, ch = cell_metrics(self.font_)
        return QSize(math.ceil(cw * self.s.screen.cols), math.ceil(ch * self.s.screen.rows))

    def sizeHint(self) -> QSize:
        return self.base_size()

    def cell_size(self) -> tuple[float, float]:
        return self.cw, self.ch

    # ----------------------------------------------------------------- input
    def _blocked(self) -> bool:
        if self.locked:
            self.notice.emit("自動輸入／登入進行中，鍵盤與捲動已暫停（可按「取消輸入」）。")
        return self.locked

    def keyPressEvent(self, e):
        if self._blocked():
            e.accept()
            return
        data, why = key_to_bytes(e.key(), e.modifiers(), e.text())
        if why:
            self.notice.emit(why)
        if data:
            if not self.s.send_user_bytes(data):
                self.notice.emit("尚未連線，按鍵未送出。")
            e.accept()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        """Touchpad / mouse wheel scrolls like the arrow keys (laptops have no PgUp/PgDn)."""
        if self.locked:
            e.accept()
            return
        self._wheel = getattr(self, "_wheel", 0) + e.angleDelta().y()
        steps = int(self._wheel / 60)
        if steps:
            self._wheel -= steps * 60
            if self.s.send_user_bytes((b"\x1b[A" if steps > 0 else b"\x1b[B") * min(abs(steps), 5)) is False:
                self.notice.emit("尚未連線，捲動未送出。")
        e.accept()

    def inputMethodEvent(self, e):
        if self._blocked():
            e.accept()
            return
        text = e.commitString()
        if text:
            try:
                data = text.encode("cp950")
            except UnicodeEncodeError:
                self.notice.emit("輸入含有無法以 Big5 編碼的字元，已忽略。")
            else:
                self.s.send_user_bytes(data)
        e.accept()

    def inputMethodQuery(self, q):
        if q == Qt.InputMethodQuery.ImCursorRectangle:
            c = self.s.screen.cur
            return QRectF(self.ox + c.x * self.cw, self.oy + c.y * self.ch, self.cw, self.ch).toRect()
        return super().inputMethodQuery(q)

    # ----------------------------------------------------------------- paint
    def _advance(self, fm: QFontMetricsF, c: str) -> float:
        a = self._adv.get(c)
        if a is None:
            a = self._adv[c] = fm.horizontalAdvance(c)
        return a

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setFont(self.draw_font)
        scr, cw, ch = self.s.screen, self.cw, self.ch
        fm = QFontMetricsF(self.draw_font)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        p.translate(self.ox, self.oy)
        sx = self.sx
        center = int(Qt.AlignmentFlag.AlignCenter)
        for y, row in enumerate(scr.grid):
            top = y * ch
            for x, (c, fg, bg, fl) in enumerate(row):
                if fl & WIDE2:
                    continue
                cells = 2 if x + 1 < len(row) and row[x + 1][3] & WIDE2 else 1
                left, w = x * cw, cells * cw
                f = BRIGHT[fg] if fl & BOLD else NORMAL[fg]
                b = NORMAL[bg]
                if fl & REVERSE:
                    f, b = b, f
                if b != (0, 0, 0):
                    p.fillRect(QRectF(left, top, w + 0.6, ch + 0.6), QColor(*b))   # +0.6: no hairline gaps between cells
                if c.strip():
                    p.setPen(QColor(*f))
                    if draw_special(p, c, QRectF(left, top, w, ch), QColor(*f)):
                        continue
                    p.setPen(QColor(*f))
                    adv = self._advance(fm, c) * sx
                    k = sx if adv <= w * 1.04 else w / self._advance(fm, c)     # squeeze glyphs wider than their cell
                    p.save()
                    p.translate(left, top)
                    p.scale(k, self.sy)
                    p.drawText(QRectF(0, 0, w / k, ch / self.sy), center, c)
                    p.restore()
                    if fl & UNDERLINE:
                        p.drawLine(int(left), int(top + ch - 2), int(left + w), int(top + ch - 2))
        cur = scr.cur
        p.setPen(QPen(QColor(255, 255, 255) if self.hasFocus() else QColor(120, 120, 120), 1))
        p.drawRect(QRectF(cur.x * cw, cur.y * ch, cw - 1, ch - 1))
        p.end()
