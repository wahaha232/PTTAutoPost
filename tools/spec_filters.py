"""Pure PyInstaller collection filters, kept importable so tests can guard them.

The PyInstaller hooks pull in every Qt DLL/plugin they can find. These filters drop
components the app never uses, while deliberately keeping the Windows platform plugin
and the TLS backends (WebSocket/wss needs them). OpenSSL DLLs are deduplicated to one
copy per library.
"""
from __future__ import annotations

OPENSSL_DLLS = ("libcrypto-3.dll", "libssl-3.dll")

# Plugins the app never loads: TUIO touch, the network-information service, the Qt
# virtual keyboard and the certificate-only TLS backend.  TLS handshakes use the
# OpenSSL/SChannel backends below, which stay.
REMOVE_NAMES = {
    "opengl32sw.dll", "qtuiotouchplugin.dll", "qnetworklistmanager.dll",
    "qcertonlybackend.dll", "qtvirtualkeyboardplugin.dll",
}

# The real GUI plugin plus the offscreen plugin used by `--selftest`; qminimal and the
# Direct2D alternative are not selected by this app.
KEEP_PLATFORM_PLUGINS = {"qwindows.dll", "qoffscreen.dll"}

# The in-app image viewer needs the common web image decoders; PNG/BMP are built
# into QtGui, so only the plugin formats are kept.  Large/rare plugins (TIFF, PDF,
# SVG, TGA, ...) stay out of the portable package.
KEEP_IMAGE_PLUGINS = {"qjpeg.dll", "qgif.dll", "qwebp.dll"}

# Qt's own right-click menus and standard buttons should be Traditional Chinese.
KEEP_TRANSLATIONS = {"qtbase_zh_TW.qm"}

REMOVE_PREFIXES = (
    "PySide6/Qt6Qml", "PySide6/Qt6Quick", "PySide6/Qt6Pdf", "PySide6/Qt6OpenGL",
    "PySide6/Qt6Svg", "PySide6/Qt6VirtualKeyboard",
    "PySide6/plugins/iconengines/", "PySide6/plugins/sqldrivers/",
    "PySide6/plugins/multimedia/", "PySide6/plugins/position/",
    "PySide6/plugins/sensors/", "PySide6/plugins/canbus/",
    "PySide6/plugins/designer/", "PySide6/plugins/qmltooling/",
    "PySide6/plugins/sceneparsers/", "PySide6/plugins/renderers/",
    "PySide6/plugins/geometryloaders/", "PySide6/plugins/texttospeech/",
    "PySide6/plugins/webview/", "PySide6/plugins/assetimporters/",
)


def normalize(name: str) -> str:
    return str(name).replace("\\", "/")


def base_name(name: str) -> str:
    return normalize(name).rsplit("/", 1)[-1]


def keep_entry(entry) -> bool:
    """entry is a PyInstaller TOC tuple; entry[0] is the destination name."""
    name = normalize(entry[0])
    base = base_name(name)
    if base.lower().endswith(".pdb"):          # debug symbols are never loaded
        return False
    if base in REMOVE_NAMES:
        return False
    if name.startswith("PySide6/plugins/platforms/"):
        return base in KEEP_PLATFORM_PLUGINS
    if name.startswith("PySide6/plugins/imageformats/"):
        return base in KEEP_IMAGE_PLUGINS
    if name.startswith("PySide6/translations/"):
        return base in KEEP_TRANSLATIONS
    return not any(name.startswith(prefix) for prefix in REMOVE_PREFIXES)


def filter_entries(entries) -> list:
    """Drop unused Qt files and keep exactly one copy of each OpenSSL DLL."""
    kept = [entry for entry in entries if keep_entry(entry)]
    chosen: dict[str, int] = {}
    for index, entry in enumerate(kept):
        base = base_name(entry[0])
        if base not in OPENSSL_DLLS:
            continue
        depth = normalize(entry[0]).count("/")
        if base not in chosen or depth < normalize(kept[chosen[base]][0]).count("/"):
            chosen[base] = index
    out = []
    for index, entry in enumerate(kept):
        base = base_name(entry[0])
        if base in OPENSSL_DLLS and chosen.get(base) != index:
            continue
        out.append(entry)
    return out
