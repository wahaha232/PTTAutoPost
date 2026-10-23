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


def test_download_without_digest_is_unverified(monkeypatch, tmp_path):
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", 3)
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: FakeResp(chunks=[b"abc"]))
    result = update.download_asset(asset, dest=tmp_path)
    assert not result.verified and result.path.exists()


def test_download_digest_mismatch_removes_the_file(monkeypatch, tmp_path):
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", 3, "sha256:" + "0" * 64)
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: FakeResp(chunks=[b"abc"]))
    with pytest.raises(update.UpdateError):
        update.download_asset(asset, dest=tmp_path)
    assert not (tmp_path / asset.name).exists()
    assert not (tmp_path / (asset.name + ".part")).exists()


def test_download_size_limit_removes_the_file(monkeypatch, tmp_path):
    asset = update.Asset("PTTAutoPost-9.9.9-portable.zip", "https://github.com/a.zip", 6)
    monkeypatch.setattr(update, "MAX_ASSET_BYTES", 5)
    monkeypatch.setattr(update.requests, "get", lambda *a, **k: FakeResp(chunks=[b"abcdef"]))
    with pytest.raises(update.UpdateError):
        update.download_asset(asset, dest=tmp_path)
    assert not (tmp_path / asset.name).exists()


def test_download_rejects_non_github_urls(tmp_path):
    asset = update.Asset("x.zip", "https://example.com/x.zip", 1)
    with pytest.raises(update.UpdateError):
        update.download_asset(asset, dest=tmp_path)
