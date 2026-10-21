"""Render assets/icon.ico (PNG-compressed multi-size ICO) from src/ui/icon.py. Offscreen; shows nothing."""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from src.ui.icon import SIZES, render  # noqa: E402


def main() -> None:
    _app = QGuiApplication([])
    pngs = []
    for n in SIZES:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        render(n).save(buf, "PNG")
        pngs.append((n, bytes(ba)))
    out = bytearray(struct.pack("<HHH", 0, 1, len(pngs)))
    off = 6 + 16 * len(pngs)
    for n, data in pngs:
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), off)
        off += len(data)
    for _n, data in pngs:
        out += data
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "icon.ico").write_bytes(out)
    (ROOT / "assets" / "icon.png").write_bytes(pngs[-1][1])
    print("wrote assets/icon.ico", len(out), "bytes")


if __name__ == "__main__":
    main()
