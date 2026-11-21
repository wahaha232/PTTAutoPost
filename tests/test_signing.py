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


RFC_VECTORS = [
    (bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"),
     bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"),
     b"\x72",
     bytes.fromhex("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
                   "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")),
    (bytes.fromhex("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7"),
     bytes.fromhex("fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025"),
     bytes.fromhex("af82"),
     bytes.fromhex("6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
                   "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a")),
    (bytes.fromhex("833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42"),
     bytes.fromhex("ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf"),
     bytes.fromhex("ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
                   "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f"),
     bytes.fromhex("dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
                   "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704")),
]


def test_rfc8032_non_empty_vectors():
    for secret, public, message, signature in RFC_VECTORS:
        assert signing.public_key(secret) == public
        assert signing.sign(secret, message) == signature
        assert signing.verify(public, message, signature)


def test_small_order_and_non_canonical_points_are_rejected():
    identity = b"\x01" + b"\x00" * 31
    assert not signing.verify(identity, b"x", identity + b"\x00" * 32)
    assert not signing.verify(PUBLIC, b"", identity + b"\x00" * 32)
    non_canonical = (2 ** 255 - 19).to_bytes(32, "little")
    assert not signing.verify(non_canonical, b"", SIG)


def test_wrong_public_key_r_point_and_malformed_signature_are_rejected():
    other_public = RFC_VECTORS[0][1]
    assert not signing.verify(other_public, b"", SIG)
    assert not signing.verify(PUBLIC, b"", bytes([SIG[0] ^ 1]) + SIG[1:])
    assert not signing.verify(PUBLIC, b"", SIG[:32] + b"\x00" * 32)
    assert not signing.verify(PUBLIC, b"", bytes(64))


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


def test_asset_rejects_a_wrong_signature_file():
    digest = hashlib.sha256(b"zip").hexdigest()
    assert not signing.verify_asset("PTTAutoPost-9.9.9-portable.zip", digest, bytes(64), PUBLIC.hex())


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
