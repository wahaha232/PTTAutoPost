# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: single-file, windowed. Excludes the many unrelated packages of the shared global Python.
from pathlib import Path

ROOT = Path(SPECPATH).resolve()  # noqa: F821

EXCLUDES = [
    "pandas", "numpy", "scipy", "matplotlib", "sympy", "onnxruntime", "cv2", "PIL", "fitz", "pymupdf", "openpyxl", "xlrd",
    "reportlab", "pikepdf", "pypdf", "docx", "markitdown", "magika", "oletools", "msoffcrypto", "IPython", "pytest", "hypothesis",
    "tkinter", "unittest", "pydoc", "setuptools", "pip", "win32com", "yaml", "cryptography",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSpatialAudio", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["PySide6.QtWebSockets", "PySide6.QtNetwork", "lxml.etree", "lxml._elementpath", "charset_normalizer"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz, a.scripts, a.binaries, a.datas, [],
    name="PTTAutoPost",
    debug=False, bootloader_ignore_signals=False, strip=False,
    upx=False,                     # UPX raises antivirus false positives; not used
    runtime_tmpdir=None,
    console=False,                 # windowed GUI app
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "icon.ico"),
)
