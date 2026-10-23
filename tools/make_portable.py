"""Build the portable package (same flow as the user's other tools: --build, assemble, --verify).

    python -X utf8 tools/make_portable.py             # build + assemble + verify
    python -X utf8 tools/make_portable.py --build     # PyInstaller (onedir) only
    python -X utf8 tools/make_portable.py --assemble  # copy the app folder + docs + data dirs
    python -X utf8 tools/make_portable.py --verify    # run the packaged exe's self-test and check contents
    python -X utf8 tools/make_portable.py --archive   # LZMA2 .7z archive for download
    python -X utf8 tools/make_portable.py --installer # LZMA2 Inno Setup installer (requires ISCC)
    python -X utf8 tools/make_portable.py --onefile   # diagnostic single-file build (default: onedir)

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
from tools.spec_filters import KEEP_IMAGE_PLUGINS, base_name  # noqa: E402

DIST = ROOT / "dist"
BUILD_OUT = DIST / f"build-{__version__}"          # versioned: a running older copy never blocks a build
APP_DIR = BUILD_OUT / "PTTAutoPost"                 # PyInstaller onedir output
PORTABLE = DIST / f"PTTAutoPost-{__version__}-portable"
EXE = "PTTAutoPost.exe"
DOCS = ("LICENSE", "THIRD_PARTY_NOTICES.md")
ARCHIVE = DIST / f"PTTAutoPost-{__version__}-portable.7z"
ZIP_ARCHIVE = DIST / f"PTTAutoPost-{__version__}-portable.zip"
ISCC_CANDIDATES = (
    Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6/ISCC.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe",
)


def readme_text() -> str:
    template = (ROOT / "USER_README.txt").read_text(encoding="utf-8")
    return template.format(version=__version__, build_date=BUILD_DATE)


def folder_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def build(onefile: bool = False):
    cmd = [sys.executable, "-X", "utf8", "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(BUILD_OUT),
           "--workpath", str(ROOT / "build"), str(ROOT / "PTTAutoPost.spec")]
    env = dict(os.environ, PTTAUTOPOST_ONEFILE="1" if onefile else "0")
    print(" ".join(cmd), "(onefile)" if onefile else "(onedir)")
    return subprocess.call(cmd, cwd=ROOT, env=env)


def assemble(onefile: bool = False):
    src = BUILD_OUT / EXE if onefile else APP_DIR
    exe = src if onefile else src / EXE
    if not exe.exists():
        print("missing", exe, "- run --build first")
        return 1
    if PORTABLE.exists():
        shutil.rmtree(PORTABLE)
    if onefile:
        PORTABLE.mkdir(parents=True)
        shutil.copy2(exe, PORTABLE / EXE)
    else:
        shutil.copytree(src, PORTABLE)
    for d in ("config", "logs", "data"):
        (PORTABLE / d).mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", PORTABLE / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", PORTABLE / "THIRD_PARTY_NOTICES.md")
    if (PORTABLE / "licenses").exists():
        shutil.rmtree(PORTABLE / "licenses")
    shutil.copytree(ROOT / "licenses", PORTABLE / "licenses")
    readme = readme_text()
    if onefile:
        readme += ("\n【注意】此為 --onefile 診斷建置：Qt 與函式庫包在單一 EXE 內，無法直接替換；"
                   "正式散布請使用預設的資料夾版。\n")
    (PORTABLE / "README.txt").write_text(readme, encoding="utf-8")
    print("assembled", PORTABLE, f"{folder_size(PORTABLE) / 1024 / 1024:.1f} MB", "(onefile)" if onefile else "(onedir)")
    return 0


def layout_report(path: Path, onefile: bool = False) -> dict:
    """Checks that depend on the onedir layout (skipped for a onefile diagnostic build)."""
    if onefile:
        return {"replaceable": True, "platform": True, "tls": True, "unused": []}
    qt_dlls = [p for p in path.rglob("Qt6Core.dll") if p.is_file()]
    tls_dir = path / "_internal/PySide6/plugins/tls"
    unused = [p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file() and (
        p.name in ("opengl32sw.dll", "Qt6Quick.dll", "Qt6Qml.dll", "Qt6Pdf.dll", "Qt6OpenGL.dll", "Qt6Svg.dll")
        or ("plugins/imageformats/" in p.as_posix() and base_name(p.name) not in KEEP_IMAGE_PLUGINS)
        or "translations/" in p.as_posix())]
    return {
        "replaceable": bool(qt_dlls) and (path / "_internal").is_dir() and all(p.parent != path for p in qt_dlls),
        "platform": (path / "_internal/PySide6/plugins/platforms/qwindows.dll").is_file(),
        "tls": tls_dir.is_dir() and any(tls_dir.glob("*.dll")),
        "unused": unused,
    }


def verify(onefile: bool = False):
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
    layout = layout_report(PORTABLE, onefile)
    replaceable, platform_ok, tls_ok, unused = (layout["replaceable"], layout["platform"], layout["tls"], layout["unused"])
    print("selftest:", "OK" if ok else "FAIL", "| mode:", "onefile" if onefile else "onedir",
          "| corpus files:", len(leaked), "| missing docs:", len(missing_docs),
          "| replaceable Qt DLLs:", replaceable, "| qwindows:", platform_ok, "| tls plugins:", tls_ok,
          "| unused Qt files:", len(unused), "| size:", f"{folder_size(PORTABLE) / 1024 / 1024:.1f} MB")
    return 0 if (ok and not leaked and not missing_docs and replaceable and platform_ok and tls_ok and not unused) else 1


def find_7z() -> str:
    found = shutil.which("7z") or shutil.which("7za")
    if found:
        return found
    default = Path(os.environ.get("ProgramFiles", "")) / "7-Zip/7z.exe"
    return str(default) if default.is_file() else ""


def make_zip():
    if ZIP_ARCHIVE.exists():
        ZIP_ARCHIVE.unlink()
    path = shutil.make_archive(str(ZIP_ARCHIVE.with_suffix("")), "zip",
                               root_dir=str(PORTABLE.parent), base_dir=PORTABLE.name)
    print("zip", path, f"{Path(path).stat().st_size / 1024 / 1024:.1f} MB")
    return path


def archive():
    if not (PORTABLE / EXE).exists():
        print("missing", PORTABLE / EXE, "- run --assemble first")
        return 1
    seven = find_7z()
    if not seven:
        make_zip()
        print("7-Zip not found; ZIP is the fallback (not LZMA2).")
        return 0
    if ARCHIVE.exists():
        ARCHIVE.unlink()
    cmd = [seven, "a", "-t7z", "-m0=lzma2", "-mx=9", str(ARCHIVE), PORTABLE.name]
    print(" ".join(cmd))
    rc = subprocess.call(cmd, cwd=DIST)
    if rc == 0:
        print("archive", ARCHIVE, f"{ARCHIVE.stat().st_size / 1024 / 1024:.1f} MB")
        make_zip()
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
    ap.add_argument("--onefile", action="store_true", help="diagnostic single-file build (default: onedir folder)")
    a = ap.parse_args()
    steps = [n for n, f in (("build", a.build), ("assemble", a.assemble), ("verify", a.verify),
                            ("archive", a.archive), ("installer", a.installer)) if f]
    steps = steps or ["build", "assemble", "verify"]
    for n in steps:
        if n == "build":
            rc = build(a.onefile)
        elif n == "assemble":
            rc = assemble(a.onefile)
        elif n == "verify":
            rc = verify(a.onefile)
        else:
            rc = {"archive": archive, "installer": installer}[n]()
        if rc:
            sys.exit(rc)
