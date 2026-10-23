"""Build the portable package (same flow as the user's other tools: --build, assemble, --verify).

    python -X utf8 tools/make_portable.py             # build + assemble + verify
    python -X utf8 tools/make_portable.py --build     # PyInstaller (onedir) only
    python -X utf8 tools/make_portable.py --assemble  # copy the app folder + docs + data dirs
    python -X utf8 tools/make_portable.py --verify    # run the packaged exe's self-test and check contents
    python -X utf8 tools/make_portable.py --archive   # LZMA2 .7z archive for download
    python -X utf8 tools/make_portable.py --installer # LZMA2 Inno Setup installer (requires ISCC)

Output: dist/PTTAutoPost-<version>-portable/ (PTTAutoPost.exe, _internal/, config/, logs/, data/,
README.txt, LICENSE, THIRD_PARTY_NOTICES.md, licenses/).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.version import BUILD_DATE, __version__  # noqa: E402

DIST = ROOT / "dist"
BUILD_OUT = DIST / f"build-{__version__}"          # versioned: a running older copy never blocks a build
APP_DIR = BUILD_OUT / "PTTAutoPost"                 # PyInstaller onedir output
PORTABLE = DIST / f"PTTAutoPost-{__version__}-portable"
EXE = "PTTAutoPost.exe"
DOCS = ("LICENSE", "THIRD_PARTY_NOTICES.md")
ARCHIVE = DIST / f"PTTAutoPost-{__version__}-portable.7z"
ISCC_CANDIDATES = (
    Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6/ISCC.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe",
)


def readme_text() -> str:
    template = (ROOT / "USER_README.txt").read_text(encoding="utf-8")
    return template.format(version=__version__, build_date=BUILD_DATE)


def folder_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def build():
    cmd = [sys.executable, "-X", "utf8", "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(BUILD_OUT),
           "--workpath", str(ROOT / "build"), str(ROOT / "PTTAutoPost.spec")]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def assemble():
    src = APP_DIR
    if not (src / EXE).exists():
        print("missing", src / EXE, "- run --build first")
        return 1
    if PORTABLE.exists():
        shutil.rmtree(PORTABLE)
    shutil.copytree(src, PORTABLE)
    for d in ("config", "logs", "data"):
        (PORTABLE / d).mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", PORTABLE / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", PORTABLE / "THIRD_PARTY_NOTICES.md")
    if (PORTABLE / "licenses").exists():
        shutil.rmtree(PORTABLE / "licenses")
    shutil.copytree(ROOT / "licenses", PORTABLE / "licenses")
    (PORTABLE / "README.txt").write_text(readme_text(), encoding="utf-8")
    print("assembled", PORTABLE, f"{folder_size(PORTABLE) / 1024 / 1024:.1f} MB")
    return 0


def verify():
    exe = PORTABLE / EXE
    if not exe.exists():
        print("missing", exe)
        return 1
    home = tempfile.mkdtemp(prefix="pttpost_verify_")
    env = dict(os.environ, PTTAUTOPOST_HOME=home, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([str(exe), "--selftest"], capture_output=True, text=True, env=env, timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip()[-400:])
    ok = r.returncode == 0 and f"version={__version__}" in out and "frozen=True" in out
    leaked = [p for p in PORTABLE.rglob("*") if "corpus" in p.name.lower()]
    missing_docs = [name for name in DOCS + ("README.txt", "licenses/LGPL-3.0.txt") if not (PORTABLE / name).is_file()]
    qt_dlls = [p for p in PORTABLE.rglob("Qt6Core.dll") if p.is_file()]
    replaceable = bool(qt_dlls) and (PORTABLE / "_internal").is_dir() and all(p.parent != PORTABLE for p in qt_dlls)
    unused = [p.relative_to(PORTABLE).as_posix() for p in PORTABLE.rglob("*") if p.is_file() and (
        p.name in ("opengl32sw.dll", "Qt6Quick.dll", "Qt6Qml.dll", "Qt6Pdf.dll", "Qt6OpenGL.dll", "Qt6Svg.dll")
        or "plugins/imageformats/" in p.as_posix() or "translations/" in p.as_posix())]
    print("selftest:", "OK" if ok else "FAIL", "| corpus files:", len(leaked),
          "| missing docs:", len(missing_docs), "| replaceable Qt DLLs:", replaceable,
          "| unused Qt files:", len(unused), "| size:", f"{folder_size(PORTABLE) / 1024 / 1024:.1f} MB")
    return 0 if ok and not leaked and not missing_docs and replaceable and not unused else 1


def find_7z() -> str:
    found = shutil.which("7z") or shutil.which("7za")
    if found:
        return found
    default = Path(os.environ.get("ProgramFiles", "")) / "7-Zip/7z.exe"
    return str(default) if default.is_file() else ""


def archive():
    seven = find_7z()
    if not seven:
        print("7-Zip not found; install 7-Zip or pass the portable folder to your own LZMA2 tool.")
        return 2
    if not (PORTABLE / EXE).exists():
        print("missing", PORTABLE / EXE, "- run --assemble first")
        return 1
    if ARCHIVE.exists():
        ARCHIVE.unlink()
    cmd = [seven, "a", "-t7z", "-m0=lzma2", "-mx=9", str(ARCHIVE), PORTABLE.name]
    print(" ".join(cmd))
    rc = subprocess.call(cmd, cwd=DIST)
    if rc == 0:
        print("archive", ARCHIVE, f"{ARCHIVE.stat().st_size / 1024 / 1024:.1f} MB")
    return rc


def find_iscc() -> str:
    found = shutil.which("iscc")
    if found:
        return found
    return next((str(p) for p in ISCC_CANDIDATES if p.is_file()), "")


def installer():
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup 6 (ISCC.exe) not found. Install it from https://jrsoftware.org/isinfo.php, then rerun --installer.")
        return 2
    if not (PORTABLE / EXE).exists():
        print("missing", PORTABLE / EXE, "- run --assemble first")
        return 1
    out = DIST / "installer"
    cmd = [iscc, f"/DMyAppVersion={__version__}", f"/DMySourceDir={PORTABLE}", f"/DMyOutputDir={out}",
           str(ROOT / "tools" / "PTTAutoPost.iss")]
    print(" ".join(cmd))
    rc = subprocess.call(cmd, cwd=ROOT)
    if rc == 0:
        print("installer written to", out)
    return rc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--archive", action="store_true")
    ap.add_argument("--installer", action="store_true")
    a = ap.parse_args()
    steps = [n for n, f in (("build", a.build), ("assemble", a.assemble), ("verify", a.verify),
                            ("archive", a.archive), ("installer", a.installer)) if f]
    steps = steps or ["build", "assemble", "verify"]
    for n in steps:
        rc = {"build": build, "assemble": assemble, "verify": verify, "archive": archive, "installer": installer}[n]()
        if rc:
            sys.exit(rc)
