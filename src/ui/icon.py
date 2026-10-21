"""App icon drawn with QPainter (no image files needed at runtime); tools/make_icon.py renders it to assets/icon.ico."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

SIZES = (16, 24, 32, 48, 64, 128, 256)


def _tile(p: QPainter, px: int, top: str, bottom: str, edge: str | None) -> float:
    s = px / 256.0
    tile = QRectF(8 * s, 8 * s, 240 * s, 240 * s)
    g = QLinearGradient(0, 0, px, px)
    g.setColorAt(0, QColor(top))
    g.setColorAt(1, QColor(bottom))
    path = QPainterPath()
    path.addRoundedRect(tile, 56 * s, 56 * s)
    p.fillPath(path, g)
    if edge:
        p.setPen(QPen(QColor(edge), max(1.0, 5 * s)))
        p.drawPath(path)
    return s


def _letter_p(p: QPainter, s: float, color: QColor, x0: float = 0, y0: float = 0, k: float = 1.0) -> None:
    """Blocky terminal-style 'P' on a 256 grid (offset/scale for small tray variants)."""
    for x, y, w, h in ((62, 52, 36, 152), (62, 52, 104, 36), (62, 118, 104, 36), (130, 52, 36, 102)):
        p.fillRect(QRectF((x0 + x * k) * s, (y0 + y * k) * s, w * k * s, h * k * s), color)


def render(px: int) -> QImage:
    """Application icon: blue gradient tile, white blocky 'P', amber cursor and a green 'sent' dot."""
    img = QImage(px, px, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = _tile(p, px, "#3b82f6", "#1e2a78", "#13194d")
    _letter_p(p, s, QColor("#ffffff"))
    p.fillRect(QRectF(150 * s, 192 * s, 62 * s, 16 * s), QColor("#ffb938"))            # cursor
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#34d399"))
    p.drawEllipse(QRectF(172 * s, 62 * s, 44 * s, 44 * s))                              # status dot
    p.end()
    return img


def render_tray(px: int, connected: bool = False) -> QImage:
    """Tray icon: no outline, bold flat shapes that stay legible at 16 px on light and dark taskbars.
    Green tile = connected, grey tile = not connected."""
    img = QImage(px, px, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = px / 256.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(4 * s, 4 * s, 248 * s, 248 * s), 64 * s, 64 * s)
    p.fillPath(path, QColor("#16a34a" if connected else "#6b7280"))
    _letter_p(p, s, QColor("#ffffff"), x0=-6, y0=-4, k=1.12)
    p.end()
    return img


def app_icon() -> QIcon:
    ic = QIcon()
    for n in SIZES:
        ic.addPixmap(QPixmap.fromImage(render(n)))
    return ic


def tray_icon(connected: bool = False) -> QIcon:
    ic = QIcon()
    for n in (16, 20, 24, 32, 48, 64):
        ic.addPixmap(QPixmap.fromImage(render_tray(n, connected)))
    return ic
