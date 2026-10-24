import pytest

from src.errors import FetchError, InputError
from src.net import upload as up


class Resp:
    def __init__(self, status=200, text="https://files.catbox.moe/abc.png"):
        self.status_code = status
        self.text = text
        self.closed = False

    def close(self):
        self.closed = True


def _png(tmp_path, name="a.png", data=b"png-bytes"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_host_choices_are_anonymous_https_hosts():
    keys = {key for key, _label in up.host_choices()}
    assert keys == {"catbox", "litterbox", "uguu"}
    assert "永久" in up.HOSTS["catbox"].label and "72" in up.HOSTS["litterbox"].label
    assert all(host.endpoint.startswith("https://") for host in up.HOSTS.values())


def test_upload_catbox_sends_multipart_and_returns_the_url(monkeypatch, tmp_path):
    captured = {}

    def post(url, data=None, files=None, headers=None, timeout=None, allow_redirects=None):
        captured.update(url=url, data=data, files=files, headers=headers, allow_redirects=allow_redirects)
        return Resp()

    monkeypatch.setattr(up.requests, "post", post)
    result = up.upload_image(_png(tmp_path), "catbox")
    assert result.url == "https://files.catbox.moe/abc.png"
    assert result.host == "catbox" and result.name == "a.png"
    assert captured["data"] == {"reqtype": "fileupload", "userhash": ""}
    assert captured["files"]["fileToUpload"][0] == "a.png"
    assert captured["allow_redirects"] is False
    assert captured["headers"]["User-Agent"].startswith("PTTAutoPost/")


def test_upload_rejects_a_response_from_another_host(monkeypatch, tmp_path):
    monkeypatch.setattr(up.requests, "post", lambda *a, **k: Resp(text="https://evil.example/x.png"))
    with pytest.raises(FetchError, match="非預期"):
        up.upload_image(_png(tmp_path), "catbox")


def test_upload_rejects_redirects_and_http_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(up.requests, "post", lambda *a, **k: Resp(status=302))
    with pytest.raises(FetchError, match="HTTP 302"):
        up.upload_image(_png(tmp_path), "catbox")
    monkeypatch.setattr(up.requests, "post", lambda *a, **k: Resp(status=413))
    with pytest.raises(FetchError, match="上限"):
        up.upload_image(_png(tmp_path), "catbox")


def test_upload_rejects_empty_response_and_bad_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(up.requests, "post", lambda *a, **k: Resp(text=""))
    with pytest.raises(FetchError, match="沒有回傳網址"):
        up.upload_image(_png(tmp_path), "catbox")
    bad = tmp_path / "a.txt"
    bad.write_text("x")
    with pytest.raises(InputError, match="只支援"):
        up.upload_image(bad, "catbox")


def test_upload_enforces_the_host_size_limit(monkeypatch, tmp_path):
    host = up.HOSTS["catbox"]
    monkeypatch.setitem(up.HOSTS, "catbox", up.Host(host.key, host.label, host.endpoint, host.field,
                                                    dict(host.extra), 2, host.allowed_hosts, host.retention))
    with pytest.raises(InputError, match="上限"):
        up.upload_image(_png(tmp_path, data=b"12345"), "catbox")


def test_batch_continues_after_a_failure(monkeypatch, tmp_path):
    def fake(path, key):
        if str(path).endswith("bad.png"):
            raise FetchError("圖床忙碌。", "429")
        return up.UploadResult("ok.png", "https://files.catbox.moe/ok.png", key, 3)

    monkeypatch.setattr(up, "upload_image", fake)
    batch = up.upload_images([str(tmp_path / "bad.png"), str(tmp_path / "ok.png")], "catbox")
    assert len(batch.results) == 1 and len(batch.errors) == 1
    assert batch.errors[0][0] == "bad.png" and "忙碌" in batch.errors[0][1]
