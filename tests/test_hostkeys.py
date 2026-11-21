import base64
import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from src.net import hostkeys


def _fp(blob: bytes) -> str:
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


def _key(host="ptt.cc", port=22, key_type="ssh-ed25519", blob=b"key-material"):
    token = f"[{host.lower()}]:{port}" if port != 22 else host.lower()
    line = f"{token} {key_type} {base64.b64encode(blob).decode()}"
    return hostkeys.HostKey(host.lower(), port, key_type, _fp(blob), line)


def _store(tmp_path):
    return hostkeys.HostKeyStore(tmp_path / "ssh_host_keys.json")


def _known(tmp_path):
    return tmp_path / "ssh_known_hosts"


def test_scan_prefers_ed25519_and_computes_sha256(monkeypatch):
    rsa = base64.b64encode(b"rsa").decode()
    ed = base64.b64encode(b"ed25519").decode()
    out = f"ptt.cc ssh-rsa {rsa}\nptt.cc ssh-ed25519 {ed}\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=out, stderr=""))
    key = hostkeys.scan_host_key("PTT.CC", 22, which=lambda _name: "ssh-keyscan")
    assert key.host == "ptt.cc" and key.port == 22 and key.key_type == "ssh-ed25519"
    assert key.fingerprint == _fp(b"ed25519")
    assert key.line == f"ptt.cc ssh-ed25519 {ed}"


def test_scan_missing_tool_failure_and_no_key(monkeypatch):
    with pytest.raises(hostkeys.HostKeyError, match="ssh-keyscan"):
        hostkeys.scan_host_key("ptt.cc", 22, which=lambda _name: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"))
    with pytest.raises(hostkeys.HostKeyError, match="結束碼 1"):
        hostkeys.scan_host_key("ptt.cc", 22, which=lambda _name: "ssh-keyscan")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="# only comments\n", stderr=""))
    with pytest.raises(hostkeys.HostKeyError, match="沒有回傳"):
        hostkeys.scan_host_key("ptt.cc", 22, which=lambda _name: "ssh-keyscan")


def test_scan_timeout_is_a_host_key_error(monkeypatch):
    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired("ssh-keyscan", 5)
    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(hostkeys.HostKeyError, match="TimeoutExpired"):
        hostkeys.scan_host_key("ptt.cc", 22, which=lambda _name: "ssh-keyscan")


def test_first_use_accept_stores_key_and_writes_project_known_hosts(tmp_path):
    prompts = []
    ok, reason = hostkeys.verify_host_key(
        "ptt.cc", 22, lambda *args: prompts.append(args) or True,
        _store(tmp_path), _known(tmp_path), scan=lambda _h, _p: _key())
    assert ok and "已信任" in reason
    assert prompts == [("ptt.cc", 22, "ssh-ed25519", _fp(b"key-material"), False)]
    record = _store(tmp_path).load()["ptt.cc:22"]
    assert record["fingerprint"] == _fp(b"key-material")
    assert "ptt.cc ssh-ed25519" in _known(tmp_path).read_text(encoding="utf-8")


def test_first_use_reject_writes_nothing(tmp_path):
    ok, reason = hostkeys.verify_host_key(
        "ptt.cc", 22, lambda *_args: False, _store(tmp_path), _known(tmp_path),
        scan=lambda _h, _p: _key())
    assert not ok and "拒絕" in reason
    assert not _store(tmp_path).path.exists() and not _known(tmp_path).exists()


def test_trusted_key_needs_no_second_prompt(tmp_path):
    store, known = _store(tmp_path), _known(tmp_path)
    assert hostkeys.verify_host_key("ptt.cc", 22, lambda *_a: True, store, known,
                                    scan=lambda _h, _p: _key())[0]
    ok, _reason = hostkeys.verify_host_key(
        "ptt.cc", 22, lambda *_a: (_ for _ in ()).throw(AssertionError("prompted again")),
        store, known, scan=lambda _h, _p: _key())
    assert ok


def test_changed_key_requires_confirmation_and_can_be_rejected(tmp_path):
    store, known = _store(tmp_path), _known(tmp_path)
    assert hostkeys.verify_host_key("ptt.cc", 22, lambda *_a: True, store, known,
                                    scan=lambda _h, _p: _key(blob=b"old"))
    seen = []
    ok, reason = hostkeys.verify_host_key(
        "ptt.cc", 22, lambda *args: seen.append(args) or False, store, known,
        scan=lambda _h, _p: _key(blob=b"new"))
    assert not ok and "變更" in reason
    assert seen[0][4] is True and seen[0][3] == _fp(b"new")
    assert store.load()["ptt.cc:22"]["fingerprint"] == _fp(b"old")


def test_changed_key_is_replaced_only_after_acceptance(tmp_path):
    store, known = _store(tmp_path), _known(tmp_path)
    assert hostkeys.verify_host_key("ptt.cc", 22, lambda *_a: True, store, known,
                                    scan=lambda _h, _p: _key(blob=b"old"))
    ok, _reason = hostkeys.verify_host_key(
        "ptt.cc", 22, lambda *args: args[4] is True, store, known,
        scan=lambda _h, _p: _key(blob=b"new"))
    assert ok
    assert store.load()["ptt.cc:22"]["fingerprint"] == _fp(b"new")
    assert base64.b64encode(b"new").decode() in known.read_text(encoding="utf-8")


def test_different_ports_are_stored_separately(tmp_path):
    store, known = _store(tmp_path), _known(tmp_path)
    asked = []
    prompt = lambda *args: asked.append((args[1], args[4])) or True
    assert hostkeys.verify_host_key("ptt.cc", 22, prompt, store, known,
                                    scan=lambda _h, _p: _key(port=22))[0]
    assert hostkeys.verify_host_key("ptt.cc", 2222, prompt, store, known,
                                    scan=lambda _h, p: _key(port=p))[0]
    assert asked == [(22, False), (2222, False)]
    assert set(store.load()) == {"ptt.cc:22", "ptt.cc:2222"}
    text = known.read_text(encoding="utf-8")
    assert "ptt.cc ssh-ed25519" in text and "[ptt.cc]:2222 ssh-ed25519" in text


def test_corrupt_store_is_moved_aside_and_reprompts(tmp_path):
    store, known = _store(tmp_path), _known(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")
    prompts = []
    ok, _reason = hostkeys.verify_host_key(
        "ptt.cc", 22, lambda *args: prompts.append(args) or True, store, known,
        scan=lambda _h, _p: _key())
    assert ok and prompts and prompts[0][4] is False
    assert (tmp_path / "ssh_host_keys.json.corrupt").exists()
    json.loads(store.path.read_text(encoding="utf-8"))


def test_keyscan_failure_fails_closed_without_prompt(tmp_path):
    prompts = []

    def fail(_h, _p):
        raise hostkeys.HostKeyError("找不到 ssh-keyscan")
    ok, reason = hostkeys.verify_host_key("ptt.cc", 22, lambda *args: prompts.append(args) or True,
                                          _store(tmp_path), _known(tmp_path), scan=fail)
    assert not ok and "ssh-keyscan" in reason and not prompts


def test_prompt_failure_fails_closed(tmp_path):
    def prompt(*_args):
        raise RuntimeError("dialog crashed")
    ok, reason = hostkeys.verify_host_key("ptt.cc", 22, prompt, _store(tmp_path), _known(tmp_path),
                                          scan=lambda _h, _p: _key())
    assert not ok and "RuntimeError" in reason


def test_user_openssh_known_hosts_is_never_touched(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    user_known = ssh_dir / "known_hosts"
    user_known.write_text("sentinel ssh-ed25519 AAAA\n", encoding="utf-8")
    before = user_known.read_text(encoding="utf-8")
    assert hostkeys.verify_host_key("ptt.cc", 22, lambda *_a: True, _store(tmp_path), _known(tmp_path),
                                    scan=lambda _h, _p: _key())[0]
    assert user_known.read_text(encoding="utf-8") == before
