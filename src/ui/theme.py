"""Application and terminal themes.

The Qt widgets use a QPalette plus a small stylesheet; the terminal is painted by TerminalWidget and gets its
own ANSI palette (a light terminal needs dark foregrounds and pale background colours to stay readable).
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

CHOICES = (("system", "跟隨系統"), ("light", "淺色"), ("dark", "深色"))
CHOICE_KEYS = tuple(k for k, _ in CHOICES)
CHOICE_LABELS = dict(CHOICES)

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class TerminalPalette:
    bg: RGB
    normal: tuple[RGB, ...]
    bright: tuple[RGB, ...]
    bg_colors: tuple[RGB, ...]
    cursor: RGB


@dataclass(frozen=True)
class Theme:
    name: str
    window: str
    base: str
    alt: str
    text: str
    muted: str
    border: str
    success: str
    warning: str
    error: str
    info: str
    on_info: str
    terminal: TerminalPalette


_DARK_TERMINAL = TerminalPalette(
    bg=(0, 0, 0),
    normal=((0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
            (40, 80, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229)),
    bright=((127, 127, 127), (255, 60, 60), (60, 255, 60), (255, 255, 60),
            (100, 120, 255), (255, 60, 255), (60, 255, 255), (255, 255, 255)),
    bg_colors=((0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
               (40, 80, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229)),
    cursor=(255, 255, 255),
)

# Light terminal: dark foregrounds, pale ANSI backgrounds; the default background is near-white.
_LIGHT_TERMINAL = TerminalPalette(
    bg=(250, 250, 250),
    normal=((20, 20, 20), (160, 0, 0), (0, 105, 0), (110, 85, 0),
            (0, 55, 165), (135, 0, 135), (0, 100, 110), (65, 65, 65)),
    bright=((75, 75, 75), (195, 0, 0), (0, 120, 0), (135, 100, 0),
            (0, 70, 190), (165, 0, 165), (0, 120, 130), (35, 35, 35)),
    bg_colors=((250, 250, 250), (255, 222, 222), (220, 246, 220), (250, 246, 210),
               (220, 236, 255), (250, 222, 250), (220, 246, 246), (236, 236, 236)),
    cursor=(20, 20, 20),
)

LIGHT = Theme(
    name="light",
    window="#f3f3f3",
    base="#ffffff",
    alt="#e9e9e9",
    text="#1b1b1b",
    muted="#666666",
    border="#bdbdbd",
    success="#1b5e20",
    warning="#8a4b00",
    error="#b71c1c",
    info="#0d47a1",
    on_info="#ffffff",
    terminal=_LIGHT_TERMINAL,
)

DARK = Theme(
    name="dark",
    window="#1e1e1e",
    base="#252526",
    alt="#2d2d30",
    text="#e8e8e8",
    muted="#a0a0a0",
    border="#414146",
    success="#81c784",
    warning="#ffb74d",
    error="#ef9a9a",
    info="#64b5f6",
    on_info="#101010",
    terminal=_DARK_TERMINAL,
)

THEMES = {"light": LIGHT, "dark": DARK}


def resolve_theme(choice: str, scheme=None, window_lightness: int | None = None) -> str:
    """Return 'light' or 'dark'. Unknown/system follows Qt's colour scheme, then the window palette."""
    if choice in ("light", "dark"):
        return choice
    if scheme == Qt.ColorScheme.Dark:
        return "dark"
    if scheme == Qt.ColorScheme.Light:
        return "light"
    if window_lightness is None:
        app = QGuiApplication.instance()
        if app is not None:
            window_lightness = app.palette().color(QPalette.ColorRole.Window).lightness()
    return "dark" if window_lightness is not None and window_lightness < 128 else "light"


def get_theme(name: str) -> Theme:
    return THEMES.get(name, LIGHT)


def terminal_palette(name: str) -> TerminalPalette:
    return get_theme(name).terminal


def app_palette(theme: Theme) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(theme.window))
    p.setColor(QPalette.ColorRole.WindowText, QColor(theme.text))
    p.setColor(QPalette.ColorRole.Base, QColor(theme.base))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.alt))
    p.setColor(QPalette.ColorRole.Text, QColor(theme.text))
    p.setColor(QPalette.ColorRole.Button, QColor(theme.alt))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(theme.text))
    p.setColor(QPalette.ColorRole.Highlight, QColor(theme.info))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.on_info))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.base))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(theme.text))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.muted))
    p.setColor(QPalette.ColorRole.Mid, QColor(theme.border))
    p.setColor(QPalette.ColorRole.Dark, QColor(theme.border))
    p.setColor(QPalette.ColorRole.Light, QColor(theme.base))
    return p


def stylesheet(theme: Theme) -> str:
    return f"""
    QMainWindow, QDialog, QWidget {{ background: {theme.window}; color: {theme.text}; }}
    QMenuBar, QMenu, QStatusBar {{ background: {theme.window}; color: {theme.text}; }}
    QMenuBar::item:selected, QMenu::item:selected {{ background: {theme.alt}; }}
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QFontComboBox {{
        background: {theme.base}; color: {theme.text}; border: 1px solid {theme.border};
    }}
    QComboBox QAbstractItemView {{ background: {theme.base}; color: {theme.text}; }}
    QPushButton {{
        background: {theme.alt}; color: {theme.text}; border: 1px solid {theme.border};
        padding: 3px 8px; border-radius: 3px;
    }}
    QPushButton:hover {{ background: {theme.base}; }}
    QPushButton:disabled {{ color: {theme.muted}; }}
    QGroupBox {{ border: 1px solid {theme.border}; margin-top: 8px; padding-top: 6px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {theme.text}; }}
    QTabWidget::pane {{ border: 1px solid {theme.border}; }}
    QTabBar::tab {{ background: {theme.alt}; color: {theme.text}; padding: 4px 10px; }}
    QTabBar::tab:selected {{ background: {theme.base}; }}
    QSplitter::handle {{ background: {theme.border}; }}
    QLabel {{ background: transparent; }}
    QToolTip {{ background: {theme.base}; color: {theme.text}; border: 1px solid {theme.border}; }}
    """


def apply_theme(app, name: str) -> None:
    # Applying a global stylesheet re-polishes every top-level window; in tests many windows exist, so only do it
    # when the application theme actually changes.
    if app.property("ptt_theme") == name:
        return
    theme = get_theme(name)
    app.setProperty("ptt_theme", name)
    app.setPalette(app_palette(theme))
    app.setStyleSheet(stylesheet(theme))


def _linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: RGB) -> float:
    r, g, b = (_linear(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
