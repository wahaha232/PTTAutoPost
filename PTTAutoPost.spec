# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: onedir by default; set PTTAUTOPOST_ONEFILE=1 for a single-file diagnostic build.
# Qt/PySide6 DLLs stay as separate replaceable files in onedir, which also keeps LGPL distribution simple.
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()  # noqa: F821
sys.path.insert(0, str(ROOT / "tools"))
from spec_filters import filter_entries  # noqa: E402

ONEFILE = os.environ.get("PTTAUTOPOST_ONEFILE") == "1"

EXCLUDES = [
    "pandas", "numpy", "scipy", "matplotlib", "sympy", "onnxruntime", "cv2", "fitz", "pymupdf", "openpyxl", "xlrd",
    "reportlab", "pikepdf", "pypdf", "docx", "markitdown", "magika", "oletools", "msoffcrypto", "IPython", "pytest", "hypothesis",
    "tkinter", "unittest", "pydoc", "setuptools", "pip", "win32com", "yaml", "cryptography",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebView",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.QtQuickControls2",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtUiTools", "PySide6.QtWebChannel",
    "PySide6.QtDBus", "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtPrintSupport", "PySide6.QtNetworkAuth",
    "PySide6.QtHttpServer", "PySide6.QtAxContainer", "PySide6.QtCore5Compat", "PySide6.QtShaderTools",
    "PySide6.QtLinguist", "PySide6.QtLinguistTools",
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
a.binaries = filter_entries(a.binaries)
a.datas = filter_entries(a.datas)
pyz = PYZ(a.pure)  # noqa: F821

COMMON = dict(
    name="PTTAutoPost",
    debug=False, bootloader_ignore_signals=False, strip=False,
    upx=False,                     # UPX raises antivirus false positives; not used
    console=False,                 # windowed GUI app
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "icon.ico"),
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **COMMON)  # noqa: F821
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **COMMON)  # noqa: F821
    coll = COLLECT(  # noqa: F821
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="PTTAutoPost",
    )
