from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from src.net.session import PttSession
from src.ui import theme
from src.ui.terminal_widget import TerminalWidget


def test_resolve_theme_explicit_and_system():
    assert theme.resolve_theme("light", Qt.ColorScheme.Dark) == "light"
    assert theme.resolve_theme("dark", Qt.ColorScheme.Light) == "dark"
    assert theme.resolve_theme("system", Qt.ColorScheme.Dark) == "dark"
    assert theme.resolve_theme("system", Qt.ColorScheme.Light) == "light"
    assert theme.resolve_theme("system", Qt.ColorScheme.Unknown, 240) == "light"
    assert theme.resolve_theme("system", Qt.ColorScheme.Unknown, 20) == "dark"
    assert theme.resolve_theme("unknown", Qt.ColorScheme.Light) == "light"


def test_light_terminal_ansi_colours_are_readable():
    t = theme.get_theme("light").terminal
    for rgb in t.normal + t.bright:
        assert theme.contrast_ratio(rgb, t.bg) >= 4.5, rgb
    assert theme.contrast_ratio(t.cursor, t.bg) >= 4.5


def test_terminal_palette_choice_dark_or_theme():
    light = theme.get_theme("light").terminal
    dark = theme.get_theme("dark").terminal
    assert theme.terminal_palette_for("dark", "light").bg == dark.bg
    assert theme.terminal_palette_for("theme", "light").bg == light.bg
    assert theme.terminal_palette_for("theme", "dark").bg == dark.bg
    assert theme.terminal_palette_for("neon", "light").bg == dark.bg


def test_terminal_widget_switches_palette(qapp):
    term = TerminalWidget(PttSession())
    term.set_theme("light")
    assert term.theme_name == "light"
    assert term.colors.bg == theme.get_theme("light").terminal.bg
    term.set_theme("dark")
    assert term.theme_name == "dark"
    assert term.colors.bg == (0, 0, 0)


def test_apply_theme_sets_application_palette(qapp):
    theme.apply_theme(QApplication.instance(), "light")
    assert QApplication.instance().property("ptt_theme") == "light"
    assert QApplication.instance().palette().color(QPalette.ColorRole.Window).name() == theme.LIGHT.window
    theme.apply_theme(QApplication.instance(), "dark")
    assert QApplication.instance().property("ptt_theme") == "dark"
