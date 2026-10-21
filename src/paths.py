"""Runtime paths. Portable: everything lives next to the EXE (config/, logs/, data/)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def runtime_base_dir() -> Path:
    """Frozen: folder of the EXE. Source: project root. Never uses the working directory."""
    if getattr(sys, "frozen", False):
        return Path(os.path.dirname(os.path.abspath(sys.executable)))
    return Path(__file__).resolve().parent.parent


def _writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=d, prefix=".w", delete=True):
            pass
        return True
    except OSError:
        return False


def _dir(name: str) -> Path:
    override = os.environ.get("PTTAUTOPOST_HOME")
    base = Path(override) if override else runtime_base_dir()
    d = base / name
    if _writable(d):
        return d
    fallback = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PTTAutoPost" / name
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def data_dir() -> Path:
    return _dir("data")


def logs_dir() -> Path:
    return _dir("logs")


def config_dir() -> Path:
    return _dir("config")
