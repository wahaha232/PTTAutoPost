import hashlib
import json

import pytest

from src import update


class FakeResp:
    def __init__(self, status=200, chunks=(), headers=None, url="https://api.github.com/repos/x"):
        self.status_code = status
        self._chunks = list(chunks)
        self.headers = headers or {}
        self.url = url
        self.closed = False

    def iter_content(self, _size):
        yield from self._chunks

    def close(self):
        self.closed = True


def release_payload(tag="v9.9.9"):
    return {
        "tag_name": tag, "name": f"Release {tag}", "body": "notes", "html_url": "https://github.com/x/y/releases/tag/x",
        "assets": [
            {"name": "PTTAutoPost-9.9.9-portable.zip", "browser_download_url":
                "https://github.com/wahaha232/PTTAutoPost/releases/download/v9.9.9/PTTAutoPost-9.9.9-portable.zip",
             "size": 123, "digest": "sha256:" + "a" * 64},
            {"name": "PTTAutoPost-9.9.9-setup.exe", "browser_download_url":
                "https://github.com/wahaha232/PTTAutoPost/releases/download/v9.9.9/PTTAutoPost-9.9.9-setup.exe",
             "size": 456},
            {"name": "bad.zip", "browser_download_url": "http://example.com/bad.zip", "size": 1},
        ],
    }


def test_version_parsing_and_comparison():
    assert update.parse_version("v1.2.3") == (1, 2, 3)
    assert update.parse_version("1.2") is None
    assert update.is_newer("1.2.4", "1.2.3")
    assert not update.is_newer("1.2.3", "1.2.3")
    assert not update.is_newer("bad", "1.2.3")


def test_asset_choice_by_installation_kind():
    assets = (
        update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", 10),
        update.Asset("PTTAutoPost-9.9.9-portable.7z", "https://github.com/a.7z", 10),
        update.Asset("PTTAutoPost-9.9.9-setup.exe", "https://github.com/a.exe", 10),
    )
    assert update.choose_asset(assets, False).name.endswith(".zip")
    assert update.choose_asset(assets, True).name.endswith("-setup.exe")
    assert update.choose_asset((assets[1],), False).name.endswith(".7z")
    assert update.choose_asset((), False) is None


def test_fetch_release_parses_assets_and_token(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, timeout=None, **kw):
        captured.update(url=url, headers=headers, timeout=timeout)
        return FakeResp(chunks=[json.dumps(release_payload()).encode()])

    monkeypatch.setattr(update.requests, "get", fake_get)
    rel = update.fetch_latest_release(token="secret")
    assert rel.version == "9.9.9" and rel.tag == "v9.9.9"
    assert len(rel.assets) == 2
    assert rel.assets[0].digest.startswith("sha256:")
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["url"].endswith("/releases/latest")


def test_fetch_release_explains_private_repo(monkeypatch):
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: FakeResp(status=404))
    with pytest.raises(update.UpdateError) as e:
        update.fetch_latest_release()
    assert update.TOKEN_ENV in str(e.value)


def test_download_verifies_sha256_and_reports_progress(monkeypatch, tmp_path):
    data = b"abcdef"
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", len(data),
                         "sha256:" + hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: FakeResp(
        chunks=[data[:3], data[3:]], headers={"Content-Length": str(len(data))},
        url="https://objects.githubusercontent.com/file"))
    progress = []
    result = update.download_asset(asset, dest=tmp_path, progress=lambda a, b: progress.append((a, b)))
    assert result.path.read_bytes() == data
    assert result.verified and result.size == len(data)
    assert progress and progress[-1][0] == len(data)


def test_download_follows_the_current_github_asset_cdn(monkeypatch, tmp_path):
    data = b"release-asset"
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", len(data),
                         "sha256:" + hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: FakeResp(
        chunks=[data], headers={"Content-Length": str(len(data))},
        url="https://release-assets.githubusercontent.com/github-production-release-asset/x?sig=1"))
    result = update.download_asset(asset, dest=tmp_path)
    assert result.verified and result.path.read_bytes() == data


def test_download_rejects_an_unknown_redirect(monkeypatch, tmp_path):
    asset = update.Asset("x.zip", "https://github.com/a.zip", 3, "sha256:" + "0" * 64)
    monkeypatch.setattr(update.requests, "get",
                        lambda *a, **k: FakeResp(chunks=[b"abc"], url="https://example.com/x.zip"))
    with pytest.raises(update.UpdateError, match="重新導向"):
        update.download_asset(asset, dest=tmp_path)


def test_download_without_digest_is_refused_before_any_request(monkeypatch, tmp_path):
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", 3)
    called = []
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: called.append(a) or FakeResp(chunks=[b"abc"]))
    with pytest.raises(update.UpdateError, match="SHA-256"):
        update.download_asset(asset, dest=tmp_path)
    assert called == []
    assert not (tmp_path / asset.name).exists() and not (tmp_path / (asset.name + ".part")).exists()


def test_download_digest_mismatch_removes_the_file(monkeypatch, tmp_path):
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", 3, "sha256:" + "0" * 64)
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: FakeResp(chunks=[b"abc"]))
    with pytest.raises(update.UpdateError):
        update.download_asset(asset, dest=tmp_path)
    assert not (tmp_path / asset.name).exists()
    assert not (tmp_path / (asset.name + ".part")).exists()


def test_download_size_limit_removes_the_file(monkeypatch, tmp_path):
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", 6, "sha256:" + "0" * 64)
    monkeypatch.setattr(update, "MAX_ASSET_BYTES", 5)
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: FakeResp(chunks=[b"abcdef"]))
    with pytest.raises(update.UpdateError):
        update.download_asset(asset, dest=tmp_path)
    assert not (tmp_path / asset.name).exists()


def test_download_cancel_mid_stream_removes_the_part_and_never_replaces(monkeypatch, tmp_path):
    import threading
    data = b"abcdef"
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", len(data),
                         "sha256:" + hashlib.sha256(data).hexdigest())
    cancel = threading.Event()

    class Resp(FakeResp):
        def iter_content(self, _size):
            yield data[:3]
            cancel.set()
            yield data[3:]

    monkeypatch.setattr(update.requests, "get", lambda *a, **k: Resp(
        chunks=[], headers={"Content-Length": str(len(data))},
        url="https://objects.githubusercontent.com/file"))
    with pytest.raises(update.UpdateError, match="取消"):
        update.download_asset(asset, dest=tmp_path, cancel=cancel)
    assert not (tmp_path / asset.name).exists()
    assert not (tmp_path / (asset.name + ".part")).exists()


def test_download_rejects_non_github_urls(tmp_path):
    asset = update.Asset("x.zip", "https://example.com/x.zip", 1)
    with pytest.raises(update.UpdateError):
        update.download_asset(asset, dest=tmp_path)


def test_choose_asset_prefers_a_matching_delta_for_portable(monkeypatch):
    monkeypatch.setattr(update, "can_apply_delta", lambda app_dir=None: True)
    delta = update.Asset(f"PTTAutoPost-9.9.9-delta-{update.__version__}.zip", "https://github.com/d.zip", 10)
    full = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/f.zip", 100)
    assert update.choose_asset([full, delta], installed=False) is delta
    assert update.choose_asset([full, delta], installed=True) is None      # no setup.exe in this list
    other = update.Asset("PTTAutoPost-9.9.9-delta-0.0.1.zip", "https://github.com/o.zip", 10)
    assert update.choose_asset([full, other], installed=False) is full
    monkeypatch.setattr(update, "can_apply_delta", lambda app_dir=None: False)
    assert update.choose_asset([full, delta], installed=False) is full


def _make_delta(tmp_path, files=None, base=None, version="9.9.9", delete=None) -> update.DownloadResult:
    import zipfile
    files = files or {"PTTAutoPost.exe": b"new-exe"}
    manifest = {
        "format": 1, "version": version, "base": base or update.__version__,
        "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                  for name, data in files.items()],
        "delete": delete or [],
    }
    path = tmp_path / f"PTTAutoPost-{version}-delta-{manifest['base']}.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("update.json", json.dumps(manifest))
        for name, data in files.items():
            zf.writestr(name, data)
    raw = path.read_bytes()
    return update.DownloadResult(path, hashlib.sha256(raw).hexdigest(), True, len(raw))


def test_stage_delta_extracts_only_manifest_files_and_removes_the_zip(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "updates_dir", lambda: tmp_path / "updates")
    result = _make_delta(tmp_path, files={"PTTAutoPost.exe": b"new-exe", "_internal/x.dll": b"dll"})
    staged = update.stage_delta(result)
    assert staged.version == "9.9.9" and staged.files == ("PTTAutoPost.exe", "_internal/x.dll")
    assert (staged.folder / "PTTAutoPost.exe").read_bytes() == b"new-exe"
    assert (staged.folder / "_internal" / "x.dll").read_bytes() == b"dll"
    assert not result.path.exists()


def test_stage_delta_rejects_wrong_base_traversal_and_hash(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "updates_dir", lambda: tmp_path / "updates")
    with pytest.raises(update.UpdateError, match="目前版本"):
        update.stage_delta(_make_delta(tmp_path, base="0.0.1"))
    with pytest.raises(update.UpdateError, match="不安全"):
        update.stage_delta(_make_delta(tmp_path, files={"../evil.exe": b"x"}))
    good = _make_delta(tmp_path, files={"a.exe": b"x"})
    import zipfile
    with zipfile.ZipFile(good.path, "a") as zf:                    # rewrite the same entry with other bytes
        zf.writestr("a.exe", b"tampered")
    with pytest.raises(update.UpdateError, match="驗證失敗"):
        update.stage_delta(good)


def test_stage_full_zip_strips_the_folder_and_skips_user_data(monkeypatch, tmp_path):
    import zipfile
    monkeypatch.setattr(update, "updates_dir", lambda: tmp_path / "updates")
    path = tmp_path / "full.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("PTTAutoPost-9.9.9-portable/PTTAutoPost.exe", b"exe")
        zf.writestr("PTTAutoPost-9.9.9-portable/_internal/x.dll", b"dll")
        zf.writestr("PTTAutoPost-9.9.9-portable/README.txt", b"readme")
        zf.writestr("PTTAutoPost-9.9.9-portable/config/user.cfg", b"keep")
        zf.writestr("PTTAutoPost-9.9.9-portable/data/db.sqlite", b"keep")
        zf.writestr("PTTAutoPost-9.9.9-portable/logs/app.log", b"keep")
    raw = path.read_bytes()
    result = update.DownloadResult(path, hashlib.sha256(raw).hexdigest(), True, len(raw))
    staged = update.stage_full_zip(result, "9.9.9")
    assert staged.files == ("PTTAutoPost.exe", "_internal/x.dll", "README.txt")
    assert (staged.folder / "PTTAutoPost.exe").read_bytes() == b"exe"
    assert not (staged.folder / "config").exists() and not (staged.folder / "data").exists()
    assert not result.path.exists()


def test_stage_full_zip_requires_the_exe(monkeypatch, tmp_path):
    import zipfile
    monkeypatch.setattr(update, "updates_dir", lambda: tmp_path / "updates")
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", b"x")
    raw = path.read_bytes()
    result = update.DownloadResult(path, hashlib.sha256(raw).hexdigest(), True, len(raw))
    with pytest.raises(update.UpdateError, match="PTTAutoPost.exe"):
        update.stage_full_zip(result, "9.9.9")


def test_apply_staged_update_writes_a_helper_and_launches_it(monkeypatch, tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "PTTAutoPost.exe").write_bytes(b"old")
    monkeypatch.setattr(update, "application_dir", lambda: app)
    monkeypatch.setattr(update, "updates_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(update, "is_installed", lambda app_dir=None: False)
    calls = []
    monkeypatch.setattr(update.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "PTTAutoPost.exe").write_bytes(b"new")
    staged = update.StagedUpdate(staging, "9.9.9", ("PTTAutoPost.exe",), ())
    script = update.apply_staged_update(staged)
    text = script.read_text(encoding="utf-8-sig")
    assert str(app) in text and "PTTAutoPost.exe" in text and "Start-Process" in text
    assert (tmp_path / "updates" / "backup-9.9.9").is_dir()
    assert calls and calls[0][0][0][0] == "powershell.exe"
    import subprocess as sp
    flags = calls[0][1]["creationflags"]
    assert flags & sp.CREATE_NO_WINDOW
    assert not flags & getattr(sp, "DETACHED_PROCESS", 0)
