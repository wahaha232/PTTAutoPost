from PySide6.QtWidgets import QLineEdit

from src.ui.i18n import install_qt_translations


def test_qtbase_translation_localizes_builtin_context_menus(qapp):
    assert install_qt_translations(qapp)
    line = QLineEdit()
    menu = line.createStandardContextMenu()
    texts = [action.text() for action in menu.actions()]
    assert any("複製" in text for text in texts), texts
    assert any("貼上" in text for text in texts), texts
