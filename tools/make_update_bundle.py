"""Build a small delta update ZIP between two portable builds.

The delta contains only files whose bytes changed (plus update.json).  User data
folders (config/data/logs/updates) are never part of it.  The app verifies every
manifest hash before applying anything.

Usage:
    python tools/make_update_bundle.py --new dist/PTTAutoPost-0.8.7-portable \
        --base dist/PTTAutoPost-0.8.6-portable
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.version import __version__  # noqa: E402

SKIP_TOP = {"config", "data", "logs", "updates"}
SKIP_PARTS = {"__pycache__", ".pytest_cache"}
VERSION_RE = re.compile(r"PTTAutoPost-(\d+\.\d+\.\d+)-portable$", re.I)


def _files(folder: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(folder)
        if rel.parts and rel.parts[0].lower() in SKIP_TOP:
            continue
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        out[rel.as_posix()] = path
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build(new: Path, base: Path, version: str, out: Path) -> Path:
    new_files, base_files = _files(new), _files(base)
    changed: list[tuple[str, Path, str, int]] = []
    for rel, path in sorted(new_files.items()):
        old = base_files.get(rel)
        if old is None or old.stat().st_size != path.stat().st_size or _sha256(old) != _sha256(path):
            changed.append((rel, path, _sha256(path), path.stat().st_size))
    deleted = sorted(rel for rel in base_files if rel not in new_files)
    manifest = {
        "format": 1,
        "version": version,
        "base": base.name.split("PTTAutoPost-")[-1].split("-portable")[0],
        "files": [{"path": rel, "sha256": sha, "size": size} for rel, _p, sha, size in changed],
        "delete": deleted,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("update.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for rel, path, _sha, _size in changed:
            zf.write(path, rel)
    print(f"delta {out.name}: {len(changed)} changed, {len(deleted)} deleted, "
          f"{out.stat().st_size / 1024 / 1024:.1f} MB")
    for rel, _p, _sha, size in changed:
        print(f"  {rel} ({size} bytes)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--base", required=True, action="append", type=Path)
    ap.add_argument("--version", default=__version__)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    args = ap.parse_args()
    if not args.new.is_dir():
        ap.error(f"new folder not found: {args.new}")
    for base in args.base:
        if not base.is_dir():
            ap.error(f"base folder not found: {base}")
        base_ver = VERSION_RE.search(base.name)
        if not base_ver:
            ap.error(f"cannot parse base version from folder name: {base.name}")
        out = args.out_dir / f"PTTAutoPost-{args.version}-delta-{base_ver.group(1)}.zip"
        build(args.new, base, args.version, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
