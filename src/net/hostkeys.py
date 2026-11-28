"""TOFU SSH host-key verification for the app's own known_hosts file.

The user's OpenSSH configuration and ~/.ssh/known_hosts are never read or written.  The
first connection runs ssh-keyscan, shows the key type and SHA256 fingerprint, and only
writes the key after the user accepts it.  Later connections must match the stored key;
a changed key stops the connection and asks again before the old record is replaced.

This is still trust-on-first-use: without comparing the fingerprint through an
independent channel, the first connection cannot be proven free of a man-in-the-middle.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PREFERRED_KEY_TYPES = ("ssh-ed25519", "ecdsa-sha2-nistp256", "ssh-rsa")


class HostKeyError(Exception):
    pass


@dataclass(frozen=True)
class HostKey:
    host: str
    port: int
    key_type: str
    fingerprint: str          # SHA256:...
    line: str                 # OpenSSH known_hosts line


def _fingerprint(blob: bytes) -> str:
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")


def _known_hosts_name(host: str, port: int) -> str:
    return f"[{host}]:{port}" if port != 22 else host


def scan_host_key(host: str, port: int, timeout: float = 5.0,
                  runner: Callable | None = None, which: Callable | None = None) -> HostKey:
    """Run ssh-keyscan and return the preferred host key, or raise HostKeyError."""
    runner = runner or subprocess.run
    which = which or shutil.which
    tool = which("ssh-keyscan")
    if not tool:
        raise HostKeyError("找不到 ssh-keyscan（OpenSSH 用戶端），無法驗證 SSH 主機金鑰。")
    run_kwargs = {"capture_output": True, "text": True, "timeout": timeout + 2}
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if flags:
            run_kwargs["creationflags"] = flags
    try:
        completed = runner([tool, "-p", str(port), "-T", str(max(1, int(timeout))), host], **run_kwargs)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HostKeyError(f"ssh-keyscan 無法完成（{type(e).__name__}）。") from e
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        raise HostKeyError(f"ssh-keyscan 失敗（結束碼 {completed.returncode}）"
                           + (f"：{detail[-1][:200]}" if detail else "。"))
    candidates = {}
    for raw in (completed.stdout or "").splitlines():
        parts = raw.strip().split()
        if len(parts) < 3 or parts[0].startswith("#"):
            continue
        key_type, payload = parts[1], parts[2]
        if key_type not in PREFERRED_KEY_TYPES:
            continue
        try:
            blob = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error):
            continue
        candidates[key_type] = (blob, payload)
    for key_type in PREFERRED_KEY_TYPES:
        if key_type in candidates:
            blob, payload = candidates[key_type]
            line = f"{_known_hosts_name(host.lower(), port)} {key_type} {payload}"
            return HostKey(host.lower(), port, key_type, _fingerprint(blob), line)
    raise HostKeyError("ssh-keyscan 沒有回傳可用的 SSH 主機金鑰。")


class HostKeyStore:
    """A small JSON file next to the app data; the OpenSSH file is generated from it."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError, json.JSONDecodeError):
            try:
                self.path.replace(self.path.with_suffix(self.path.suffix + ".corrupt"))
            except OSError:
                pass
            return {}

    def save(self, records: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.path, json.dumps(records, ensure_ascii=False, indent=2) + "\n")

    def write_known_hosts(self, records: dict[str, dict], target: str | Path) -> None:
        lines = [record["line"] for record in records.values() if record.get("line")]
        _atomic_write(Path(target), "\n".join(sorted(lines)) + ("\n" if lines else ""))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".hostkeys-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def verify_host_key(host: str, port: int, prompt: Callable[[str, int, str, str, bool], bool],
                    store: HostKeyStore, known_hosts_path: str | Path,
                    scan: Callable[..., HostKey] = scan_host_key) -> tuple[bool, str]:
    """Verify or TOFU-accept one host key.  `prompt(host, port, type, fingerprint, changed)` returns bool."""
    try:
        key = scan(host, port)
    except HostKeyError as e:
        return False, str(e)
    records = store.load()
    ident = f"{key.host}:{key.port}"
    old = records.get(ident)
    changed = bool(old) and (old.get("fingerprint") != key.fingerprint or old.get("key_type") != key.key_type)
    if old and not changed:
        store.write_known_hosts(records, known_hosts_path)
        return True, f"已信任 {key.key_type} {key.fingerprint}"
    try:
        accepted = bool(prompt(key.host, key.port, key.key_type, key.fingerprint, changed))
    except Exception as e:  # noqa: BLE001  (a broken prompt must fail closed)
        return False, f"無法完成主機金鑰確認（{type(e).__name__}）。"
    if not accepted:
        return False, ("主機金鑰已變更，使用者拒絕連線。" if changed else "使用者拒絕新的 SSH 主機金鑰。")
    records[ident] = {"key_type": key.key_type, "fingerprint": key.fingerprint, "line": key.line}
    store.save(records)
    store.write_known_hosts(records, known_hosts_path)
    return True, f"已信任 {key.key_type} {key.fingerprint}"
