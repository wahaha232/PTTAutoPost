"""Ed25519 signatures for update assets (RFC 8032, pure Python: no extra dependency).

Releases are signed offline with tools/sign_release.py; the app only verifies with the public key
below.  A GitHub digest proves the bytes match what the release says, a signature proves the release
was made by the holder of the private key (a stolen GitHub token alone cannot publish an update).

Signing here is not constant-time; it is only meant for the offline release tool.
"""
from __future__ import annotations

import hashlib

# Public half of the release signing key (private half is kept outside the repository).
# Rotated 2026-10-31 for 0.8.20 after the old private key was lost. 0.8.19 cannot verify this
# key, so 0.8.20 must be installed manually once; 0.8.21+ can auto-update with the new key.
UPDATE_PUBLIC_KEY_HEX = "03de7808a744259b060038ce91d599a3c60bb50c7f113b5e89338e30aab72ee0"

_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


def _sha512_modq(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little") % _Q


def _add(a, b):
    x = (a[1] - a[0]) * (b[1] - b[0]) % _P
    y = (a[1] + a[0]) * (b[1] + b[0]) % _P
    c = 2 * a[3] * b[3] * _D % _P
    d = 2 * a[2] * b[2] % _P
    e, f, g, h = y - x, d - c, d + c, y + x
    return (e * f, g * h, f * g, e * h)


def _mul(s: int, pt):
    acc = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            acc = _add(acc, pt)
        pt = _add(pt, pt)
        s >>= 1
    return acc


def _equal(a, b) -> bool:
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(pt) -> bytes:
    zinv = _inv(pt[2])
    x, y = pt[0] * zinv % _P, pt[1] * zinv % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decompress(raw: bytes):
    if len(raw) != 32:
        return None
    y = int.from_bytes(raw, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _expand(secret: bytes) -> tuple[int, bytes]:
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    if len(secret) != 32:
        raise ValueError("Ed25519 secret key must be 32 bytes")
    return _compress(_mul(_expand(secret)[0], _G))


def sign(secret: bytes, message: bytes) -> bytes:
    a, prefix = _expand(secret)
    pub = _compress(_mul(a, _G))
    r = _sha512_modq(prefix + message)
    rs = _compress(_mul(r, _G))
    s = (r + _sha512_modq(rs + pub + message) * a) % _Q
    return rs + s.to_bytes(32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    a = _decompress(public)
    r = _decompress(signature[:32])
    if a is None or r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = _sha512_modq(signature[:32] + public + message)
    return _equal(_mul(s, _G), _add(r, _mul(h, a)))


def asset_message(name: str, sha256_hex: str) -> bytes:
    """What a release signature covers: the asset file name (it carries the version) and its SHA-256."""
    return f"PTTAutoPost-update-v1\n{name}\n{sha256_hex.lower()}\n".encode("utf-8")


def verify_asset(name: str, sha256_hex: str, signature: bytes, public_hex: str | None = None) -> bool:
    try:
        public = bytes.fromhex(UPDATE_PUBLIC_KEY_HEX if public_hex is None else public_hex)
    except ValueError:
        return False
    return verify(public, asset_message(name, sha256_hex), signature)
