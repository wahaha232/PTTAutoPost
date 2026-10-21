"""Build the portable package (same flow as the user's other tools: --build, assemble, --verify).

    python -X utf8 tools/make_portable.py            # build + assemble + verify
    python -X utf8 tools/make_portable.py --build    # PyInstaller only
    python -X utf8 tools/make_portable.py --assemble # copy exe + create config/logs/data
    python -X utf8 tools/make_portable.py --verify   # run the packaged exe's self-test, check version/contents
Output: dist/PTTAutoPost-<version>-portable/  (PTTAutoPost.exe, config/, logs/, data/, README.txt)
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
from src.version import __version__  # noqa: E402

DIST = ROOT / "dist"
BUILD_OUT = DIST / f"build-{__version__}"          # versioned: a running older copy never blocks a build
PORTABLE = DIST / f"PTTAutoPost-{__version__}-portable"
EXE = "PTTAutoPost.exe"

README = """PTT AutoPost (portable) -- unzip anywhere and double-click PTTAutoPost.exe.
config/ logs/ data/ are created next to the exe; nothing is written to the registry.
Command line:  PTTAutoPost.exe --selftest   (headless smoke test)
               PTTAutoPost.exe --probe      (read-only check of wss://ws.ptt.cc/bbs; sends nothing)
The program never logs in on its own, never presses save/send in PTT, and never stores your password.
"""


def build():
    cmd = [sys.executable, "-X", "utf8", "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(BUILD_OUT),
           "--workpath", str(ROOT / "build"), str(ROOT / "PTTAutoPost.spec")]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def assemble():
    src = BUILD_OUT / EXE
    if not src.exists():
        print("missing", src, "- run --build first")
        return 1
    if PORTABLE.exists():
        shutil.rmtree(PORTABLE)
    for d in ("config", "logs", "data"):
        (PORTABLE / d).mkdir(parents=True)
    shutil.copy2(src, PORTABLE / EXE)
    (PORTABLE / "README.txt").write_text(README, encoding="utf-8")
    print("assembled", PORTABLE, f"{(PORTABLE / EXE).stat().st_size / 1024 / 1024:.1f} MB")
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
    print("selftest:", "OK" if ok else "FAIL", "| corpus files in package:", len(leaked))
    return 0 if ok and not leaked else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    steps = [n for n, f in (("build", a.build), ("assemble", a.assemble), ("verify", a.verify)) if f] or ["build", "assemble", "verify"]
    for n in steps:
        rc = {"build": build, "assemble": assemble, "verify": verify}[n]()
        if rc:
            sys.exit(rc)
