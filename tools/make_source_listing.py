"""Write a plain-text listing of the source tree for review/backup.

    python -X utf8 tools/make_source_listing.py

Output: dist/PTTAutoPost-<version>-source.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.version import __version__  # noqa: E402

DIST = ROOT / "dist"
SKIP_DIRS = {".git", "build", "dist", ".venv", "venv", "__pycache__", ".kilo", ".pytest_cache"}
SUFFIXES = {".py", ".spec", ".iss", ".bat", ".txt", ".ps1"}


def collect_files(root: Path = ROOT) -> list[Path]:
    out = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                continue
        except OSError:
            continue
        out.append(path)
    return out


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    target = DIST / f"PTTAutoPost-{__version__}-source.txt"
    files = collect_files()
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"PTT AutoPost {__version__} source listing\n")
        f.write(f"files: {len(files)}\n\n")
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            f.write("=" * 100 + "\n")
            f.write(f"FILE: {rel}\n")
            f.write("=" * 100 + "\n")
            try:
                f.write(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                f.write("(skipped: not UTF-8)\n")
            f.write("\n\n")
    print("wrote", target, f"{target.stat().st_size / 1024:.1f} KB, {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
