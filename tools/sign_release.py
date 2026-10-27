"""Create the release signing key and sign update assets.

The private key never belongs in the repository.  Keep it (and a backup) outside the project, and
point PTTAUTOPOST_SIGNING_KEY at it or pass --key.

Usage:
    python tools/sign_release.py keygen --out D:/Claude/keystore/pttautopost-update-ed25519.key
    python tools/sign_release.py sign dist/PTTAutoPost-0.8.19-portable.zip dist/PTTAutoPost-0.8.18-delta-0.8.19.zip

`sign` writes <asset>.sig next to each asset; upload every .sig to the same GitHub Release.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import signing  # noqa: E402

KEY_ENV = "PTTAUTOPOST_SIGNING_KEY"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_key(path: Path) -> bytes:
    secret = bytes.fromhex(path.read_text(encoding="ascii").strip())
    if len(secret) != 32:
        raise SystemExit(f"{path} is not a 32-byte Ed25519 secret key")
    pub = signing.public_key(secret).hex()
    if pub != signing.UPDATE_PUBLIC_KEY_HEX:
        raise SystemExit("this key does not match signing.UPDATE_PUBLIC_KEY_HEX; refusing to sign")
    return secret


def keygen(out: Path) -> None:
    if out.exists():
        raise SystemExit(f"{out} already exists; refusing to overwrite a signing key")
    out.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    out.write_text(secret.hex() + "\n", encoding="ascii")
    print(f"private key: {out}  (back it up; losing it means future releases cannot be verified)")
    print(f"public key : {signing.public_key(secret).hex()}  -> put in src/signing.py UPDATE_PUBLIC_KEY_HEX")


def sign_files(key: Path, files: list[Path]) -> None:
    secret = _load_key(key)
    for path in files:
        digest = _sha256(path)
        sig = signing.sign(secret, signing.asset_message(path.name, digest))
        if not signing.verify_asset(path.name, digest, sig):
            raise SystemExit(f"self-check failed for {path}")
        out = path.with_name(path.name + ".sig")
        out.write_text(sig.hex() + "\n", encoding="ascii")
        print(f"signed {path.name} -> {out.name}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("sign")
    s.add_argument("--key", type=Path, default=os.environ.get(KEY_ENV))
    s.add_argument("files", type=Path, nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "keygen":
        keygen(args.out)
    else:
        if not args.key:
            raise SystemExit(f"pass --key or set {KEY_ENV}")
        sign_files(args.key, args.files)


if __name__ == "__main__":
    main()
