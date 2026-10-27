import hashlib

from src import signing

# RFC 8032 section 7.1, TEST 1 (empty message)
SECRET = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
PUBLIC = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
SIG = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065"
                    "224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")


def test_rfc8032_vector():
    assert signing.public_key(SECRET) == PUBLIC
    assert signing.sign(SECRET, b"") == SIG
    assert signing.verify(PUBLIC, b"", SIG)


def test_tampering_is_rejected():
    assert not signing.verify(PUBLIC, b"x", SIG)
    assert not signing.verify(PUBLIC, b"", bytes([SIG[0] ^ 1]) + SIG[1:])
    assert not signing.verify(PUBLIC, b"", SIG[:32] + (2 ** 253).to_bytes(32, "little"))   # s >= q
    assert not signing.verify(PUBLIC[:31], b"", SIG) and not signing.verify(PUBLIC, b"", SIG[:63])


def test_asset_signature_binds_name_and_hash():
    digest = hashlib.sha256(b"zip").hexdigest()
    sig = signing.sign(SECRET, signing.asset_message("PTTAutoPost-9.9.9-portable.zip", digest))
    pub = PUBLIC.hex()
    assert signing.verify_asset("PTTAutoPost-9.9.9-portable.zip", digest, sig, pub)
    assert not signing.verify_asset("PTTAutoPost-9.9.8-portable.zip", digest, sig, pub)
    assert not signing.verify_asset("PTTAutoPost-9.9.9-portable.zip", "0" * 64, sig, pub)
    assert not signing.verify_asset("PTTAutoPost-9.9.9-portable.zip", digest, sig, "zz")


def test_embedded_public_key_is_a_valid_point():
    assert len(bytes.fromhex(signing.UPDATE_PUBLIC_KEY_HEX)) == 32
    assert signing._decompress(bytes.fromhex(signing.UPDATE_PUBLIC_KEY_HEX)) is not None


def test_release_tool_signs_and_refuses_a_foreign_key(tmp_path, monkeypatch):
    import pytest
    from tools import sign_release
    key = tmp_path / "k.key"
    sign_release.keygen(key)
    secret = bytes.fromhex(key.read_text(encoding="ascii").strip())
    asset = tmp_path / "PTTAutoPost-9.9.9-portable.zip"
    asset.write_bytes(b"zip")
    with pytest.raises(SystemExit, match="does not match"):
        sign_release.sign_files(key, [asset])                   # a key the app does not trust is never used
    monkeypatch.setattr(signing, "UPDATE_PUBLIC_KEY_HEX", signing.public_key(secret).hex())
    sign_release.sign_files(key, [asset])
    sig = bytes.fromhex((tmp_path / (asset.name + ".sig")).read_text(encoding="ascii").strip())
    assert signing.verify_asset(asset.name, hashlib.sha256(b"zip").hexdigest(), sig)
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        sign_release.keygen(key)
