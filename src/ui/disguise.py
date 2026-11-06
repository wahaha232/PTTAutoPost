"""Notepad-style disguise view.

The main window can replace its normal UI with this read-only plain-text view so the window looks like
Windows Notepad showing a text file.  It only ever shows text: nothing in this module can follow a link,
display an image, or start a browser.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QFrame, QPlainTextEdit, QVBoxLayout, QWidget

DISGUISE_TITLE = "備忘錄.txt - 記事本"

_EDITOR_QSS = """
QPlainTextEdit {
    background: #ffffff;
    color: #000000;
    border: 0;
    selection-background-color: #cce8ff;
    selection-color: #000000;
}
"""


def notepad_font() -> QFont:
    """A Notepad-like fixed-pitch font; CJK glyphs fall back to the system font."""
    families = set(QFontDatabase.families())
    family = next((name for name in ("MingLiU", "NSimSun", "Consolas", "Courier New") if name in families), "")
    font = QFont(family) if family else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.TypeWriter)
    font.setFixedPitch(True)
    font.setPointSize(11)
    return font


class NotepadView(QWidget):
    """Read-only white text area that mimics a Notepad window's document area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QWidget { background: #ffffff; }")
        self.editor = QPlainTextEdit(self)
        self.editor.setReadOnly(True)
        self.editor.setUndoRedoEnabled(False)
        self.editor.setFrameShape(QFrame.Shape.NoFrame)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.editor.setStyleSheet(_EDITOR_QSS)
        self.editor.setFont(notepad_font())
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.addWidget(self.editor)

    def apply_notepad_font(self) -> None:
        self.editor.setFont(notepad_font())

    def set_text(self, text: str) -> None:
        if self.editor.toPlainText() == text:
            return
        bar = self.editor.verticalScrollBar()
        position = bar.value()
        self.editor.setPlainText(text)                  # plain text only: no rich text, links, or images
        bar.setValue(min(position, bar.maximum()))

    def text(self) -> str:
        return self.editor.toPlainText()

    def set_word_wrap(self, on: bool) -> None:
        self.editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if on else QPlainTextEdit.LineWrapMode.NoWrap)
