"""Application and terminal themes powered by the open-source `qt-themes` (MIT) palettes.

Uses Qt's Fusion style, QPalette and a modern flat QSS layer (no QtSvg dependency, keeping the
portable build small). The terminal keeps its own ANSI palette so light themes stay WCAG-readable.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

try:
    import qt_themes as _qt_themes
except ImportError:  # pragma: no cover - fallback when qt-themes is not installed
    _qt_themes = None

CHOICES = (
    ("system", "跟隨系統"),
    ("light", "淺色（現代淺色）"),
    ("dark", "深色（現代深色）"),
    ("github_light", "GitHub Light（淺色）"),
    ("github_dark", "GitHub Dark（深色）"),
    ("catppuccin_latte", "Catppuccin Latte（淺色）"),
    ("catppuccin_mocha", "Catppuccin Mocha（深色）"),
    ("nord", "Nord（北歐深色）"),
    ("dracula", "Dracula（深色）"),
    ("one_dark_two", "One Dark（深色）"),
)
CHOICE_KEYS = tuple(k for k, _ in CHOICES)
CHOICE_LABELS = dict(CHOICES)

TERMINAL_PALETTE_CHOICES = (("dark", "永遠深色（黑底）"), ("theme", "跟隨主題"))
TERMINAL_PALETTE_KEYS = tuple(k for k, _ in TERMINAL_PALETTE_CHOICES)
TERMINAL_PALETTE_LABELS = dict(TERMINAL_PALETTE_CHOICES)

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
    surface: str = ""
    hover: str = ""
    info_hover: str = ""
    is_dark: bool = False


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


def _hex_to_rgb(hex_color: str) -> RGB:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


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


def _ensure_contrast(color_hex: str, bg1_hex: str, bg2_hex: str, is_dark: bool, minimum: float = 3.2) -> str:
    """Nudge a palette colour slightly lighter/darker only if needed to meet WCAG non-text contrast."""
    c = QColor(color_hex)
    bg1, bg2 = _hex_to_rgb(bg1_hex), _hex_to_rgb(bg2_hex)
    for _ in range(16):
        rgb = (c.red(), c.green(), c.blue())
        if contrast_ratio(rgb, bg1) >= minimum and contrast_ratio(rgb, bg2) >= minimum:
            return c.name()
        c = c.lighter(112) if is_dark else c.darker(114)
    return c.name()


def _on_color(bg_hex: str) -> str:
    rgb = _hex_to_rgb(bg_hex)
    return "#11111b" if contrast_ratio(rgb, (17, 17, 27)) >= contrast_ratio(rgb, (255, 255, 255)) else "#ffffff"


def _shift(hex_color: str, factor: int) -> str:
    c = QColor(hex_color)
    return (c.lighter(factor) if factor >= 100 else c.darker(int(10000 / max(factor, 1)))).name()


def _from_qt_theme(name: str, qt_key: str, fallback: Theme) -> Theme:
    """Build a `Theme` from an open-source `qt-themes` palette with guaranteed contrast."""
    if _qt_themes is None:
        return fallback
    qt_t = _qt_themes.get_theme(qt_key)
    if qt_t is None:
        return fallback
    is_dark = bool(qt_t.is_dark_theme())
    if is_dark:
        window = qt_t.mantle.name()
        base = qt_t.base.name()
        surface = qt_t.crust.name()
        alt = qt_t.surface0.name()
        hover = qt_t.surface1.name()
        border = qt_t.surface2.name()
    else:
        window = qt_t.mantle.name()
        base = qt_t.crust.name()
        surface = qt_t.base.name()
        alt = qt_t.surface0.name()
        hover = qt_t.surface1.name()
        border = qt_t.surface1.name()
    text = qt_t.text.name()
    muted = _ensure_contrast(qt_t.subtext0.name(), base, window, is_dark, minimum=3.4)
    info = _ensure_contrast(qt_t.primary.name(), base, window, is_dark, minimum=3.4)
    success = _ensure_contrast(qt_t.green.name(), base, window, is_dark, minimum=3.4)
    warning = _ensure_contrast(qt_t.orange.name(), base, window, is_dark, minimum=3.4)
    error = _ensure_contrast(qt_t.red.name(), base, window, is_dark, minimum=3.4)
    return Theme(
        name=name,
        window=window,
        base=base,
        alt=alt,
        text=text,
        muted=muted,
        border=border,
        success=success,
        warning=warning,
        error=error,
        info=info,
        on_info=_on_color(info),
        terminal=_DARK_TERMINAL if is_dark else _LIGHT_TERMINAL,
        surface=surface,
        hover=hover,
        info_hover=_shift(info, 110 if is_dark else 90),
        is_dark=is_dark,
    )


_FALLBACK_LIGHT = Theme(
    name="light",
    window="#f3f4f6",
    base="#ffffff",
    alt="#e5e7eb",
    text="#1f2328",
    muted="#59636e",
    border="#d0d7de",
    success="#1a7f37",
    warning="#9a6700",
    error="#cf222e",
    info="#0969da",
    on_info="#ffffff",
    terminal=_LIGHT_TERMINAL,
    surface="#f6f8fa",
    hover="#eaeef2",
    info_hover="#0859ba",
    is_dark=False,
)

_FALLBACK_DARK = Theme(
    name="dark",
    window="#161b22",
    base="#0d1117",
    alt="#21262d",
    text="#e6edf3",
    muted="#8b949e",
    border="#30363d",
    success="#3fb950",
    warning="#d29922",
    error="#f85149",
    info="#58a6ff",
    on_info="#0d1117",
    terminal=_DARK_TERMINAL,
    surface="#1c2128",
    hover="#30363d",
    info_hover="#79b8ff",
    is_dark=True,
)

LIGHT = _from_qt_theme("light", "modern_light", _FALLBACK_LIGHT)
DARK = _from_qt_theme("dark", "modern_dark", _FALLBACK_DARK)

THEMES: dict[str, Theme] = {
    "light": LIGHT,
    "dark": DARK,
    "github_light": _from_qt_theme("github_light", "github_light", _FALLBACK_LIGHT),
    "github_dark": _from_qt_theme("github_dark", "github_dark", _FALLBACK_DARK),
    "catppuccin_latte": _from_qt_theme("catppuccin_latte", "catppuccin_latte", _FALLBACK_LIGHT),
    "catppuccin_mocha": _from_qt_theme("catppuccin_mocha", "catppuccin_mocha", _FALLBACK_DARK),
    "nord": _from_qt_theme("nord", "nord", _FALLBACK_DARK),
    "dracula": _from_qt_theme("dracula", "dracula", _FALLBACK_DARK),
    "one_dark_two": _from_qt_theme("one_dark_two", "one_dark_two", _FALLBACK_DARK),
}


def resolve_theme(choice: str, scheme=None, window_lightness: int | None = None) -> str:
    """Return a concrete theme key. Unknown/system follows Qt's colour scheme, then window palette."""
    if choice in THEMES:
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


def terminal_palette_for(choice: str, theme_name: str) -> TerminalPalette:
    """'dark' always keeps the black ANSI palette; 'theme' follows the application theme."""
    return _DARK_TERMINAL if choice != "theme" else get_theme(theme_name).terminal


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
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.muted))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.muted))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(theme.muted))
    return p


def stylesheet(theme: Theme) -> str:
    surface = theme.surface or theme.window
    hover = theme.hover or theme.base
    info_hover = theme.info_hover or theme.info
    return f"""
    QMainWindow, QDialog, QWidget {{
        background: {theme.window};
        color: {theme.text};
    }}
    QMenuBar {{
        background: {theme.window};
        color: {theme.text};
        border-bottom: 1px solid {theme.border};
        padding: 2px 4px;
    }}
    QMenuBar::item {{
        padding: 4px 10px;
        border-radius: 5px;
    }}
    QMenuBar::item:selected {{
        background: {hover};
    }}
    QMenu {{
        background: {theme.base};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 20px 6px 12px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background: {theme.info};
        color: {theme.on_info};
    }}
    QMenu::separator {{
        height: 1px;
        background: {theme.border};
        margin: 4px 6px;
    }}
    QStatusBar {{
        background: {surface};
        color: {theme.text};
        border-top: 1px solid {theme.border};
        padding: 2px 6px;
    }}
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QFontComboBox {{
        background: {theme.base};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        padding: 4px 8px;
        selection-background-color: {theme.info};
        selection-color: {theme.on_info};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QFontComboBox:focus {{
        border: 1px solid {theme.info};
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        background: {theme.alt};
        color: {theme.muted};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {theme.base};
        color: {theme.text};
        border: 1px solid {theme.border};
        selection-background-color: {theme.info};
        selection-color: {theme.on_info};
        outline: 0;
    }}
    QPushButton {{
        background: {theme.alt};
        color: {theme.text};
        border: 1px solid {theme.border};
        padding: 5px 12px;
        border-radius: 6px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background: {hover};
        border-color: {theme.info};
    }}
    QPushButton:pressed {{
        background: {theme.base};
    }}
    QPushButton:checked {{
        background: {theme.info};
        color: {theme.on_info};
        border-color: {theme.info};
    }}
    QPushButton:disabled {{
        color: {theme.muted};
        background: {surface};
        border-color: {theme.border};
    }}
    QPushButton[variant="primary"] {{
        background: {theme.info};
        color: {theme.on_info};
        border: 1px solid {theme.info};
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: {info_hover};
        border-color: {info_hover};
    }}
    QPushButton[variant="primary"]:disabled {{
        background: {theme.alt};
        color: {theme.muted};
        border-color: {theme.border};
    }}
    QGroupBox {{
        background: {surface};
        border: 1px solid {theme.border};
        border-radius: 8px;
        margin-top: 12px;
        padding: 10px 8px 8px 8px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
        color: {theme.text};
    }}
    QTabWidget::pane {{
        border: 1px solid {theme.border};
        border-radius: 6px;
        background: {theme.window};
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {theme.muted};
        padding: 6px 14px;
        margin-right: 2px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 500;
    }}
    QTabBar::tab:hover {{
        color: {theme.text};
        background: {theme.alt};
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }}
    QTabBar::tab:selected {{
        color: {theme.text};
        background: {theme.base};
        border-bottom: 2px solid {theme.info};
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: 600;
    }}
    QListWidget, QTableWidget, QTreeWidget {{
        background: {theme.base};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 6px;
        outline: 0;
    }}
    QListWidget::item, QTableWidget::item, QTreeWidget::item {{
        padding: 4px 6px;
        border-radius: 4px;
    }}
    QListWidget::item:selected, QTableWidget::item:selected, QTreeWidget::item:selected {{
        background: {theme.info};
        color: {theme.on_info};
    }}
    QHeaderView::section {{
        background: {theme.alt};
        color: {theme.text};
        border: none;
        border-bottom: 1px solid {theme.border};
        padding: 5px 8px;
        font-weight: 600;
    }}
    QSplitter::handle {{
        background: {theme.border};
    }}
    QSplitter::handle:hover {{
        background: {theme.info};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 9px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {theme.border};
        min-height: 28px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {theme.muted};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 9px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {theme.border};
        min-width: 28px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {theme.muted};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
        width: 0px;
    }}
    QProgressBar {{
        background: {theme.alt};
        border: 1px solid {theme.border};
        border-radius: 5px;
        text-align: center;
        color: {theme.text};
    }}
    QProgressBar::chunk {{
        background: {theme.info};
        border-radius: 4px;
    }}
    QLabel {{
        background: transparent;
    }}
    QCheckBox, QRadioButton {{
        spacing: 6px;
        background: transparent;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 14px; height: 14px; background: {theme.base}; border: 1px solid {theme.muted};
    }}
    QCheckBox::indicator {{ border-radius: 3px; }}
    QRadioButton::indicator {{ border-radius: 7px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {theme.info}; }}
    QCheckBox::indicator:checked {{ background: {theme.info}; border-color: {theme.info}; }}
    QRadioButton::indicator:checked {{
        border-color: {theme.info};
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                    stop:0 {theme.info}, stop:0.5 {theme.info}, stop:0.6 {theme.base}, stop:1 {theme.base});
    }}
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
        background: {theme.alt}; border-color: {theme.border};
    }}
    QToolTip {{
        background: {theme.base};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 4px;
        padding: 4px 6px;
    }}
    """


def apply_theme(app, name: str) -> None:
    # Applying a global stylesheet re-polishes every top-level window; in tests many windows exist, so only do it
    # when the application theme actually changes.
    if app.property("ptt_theme") == name:
        return
    if not app.property("ptt_style_set"):
        app.setStyle("Fusion")
        app.setProperty("ptt_style_set", True)
    theme = get_theme(name)
    app.setProperty("ptt_theme", name)
    app.setPalette(app_palette(theme))
    app.setStyleSheet(stylesheet(theme))
