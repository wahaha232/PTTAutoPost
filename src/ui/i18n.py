"""Load Qt's Traditional Chinese catalog so built-in context menus and dialogs are localized."""
from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, QTranslator


def install_qt_translations(app) -> bool:
    """Install qtbase_zh_TW (right-click menus, standard buttons). Returns True when loaded."""
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load("qtbase_zh_TW", path):
        return False
    app.installTranslator(translator)
    app._qt_zh_tw_translator = translator     # keep a reference; QTranslator is not owned by the app
    return True
