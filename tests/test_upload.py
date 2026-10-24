import io
import threading

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


class FakeSession:
    def __init__(self, resp):
        self.resp = resp
        self.kwargs = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.kwargs = kwargs
        return self.resp


def _patch_session(monkeypatch, resp):
    fake = FakeSession(resp)
    monkeypatch.setattr(up, "_session_for", lambda url: fake)
    return fake


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
    fake = _patch_session(monkeypatch, Resp())
    result = up.upload_image(_png(tmp_path), "catbox")
    assert result.url == "https://files.catbox.moe/abc.png"
    assert result.host == "catbox" and result.name == "a.png"
    assert fake.kwargs["data"] == {"reqtype": "fileupload", "userhash": ""}
    assert fake.kwargs["files"]["fileToUpload"][0] == "a.png"
    assert fake.kwargs["allow_redirects"] is False
    assert fake.kwargs["headers"]["User-Agent"].startswith("PTTAutoPost/")


def test_upload_rejects_a_response_from_another_host(monkeypatch, tmp_path):
    _patch_session(monkeypatch, Resp(text="https://evil.example/x.png"))
    with pytest.raises(FetchError, match="非預期"):
        up.upload_image(_png(tmp_path), "catbox")


def test_upload_rejects_redirects_and_http_errors(monkeypatch, tmp_path):
    _patch_session(monkeypatch, Resp(status=302))
    with pytest.raises(FetchError, match="HTTP 302"):
        up.upload_image(_png(tmp_path), "catbox")
    _patch_session(monkeypatch, Resp(status=413))
    with pytest.raises(FetchError, match="上限"):
        up.upload_image(_png(tmp_path), "catbox")


def test_upload_rejects_empty_response_and_bad_extension(monkeypatch, tmp_path):
    _patch_session(monkeypatch, Resp(text=""))
    with pytest.raises(FetchError, match="沒有回傳網址"):
        up.upload_image(_png(tmp_path), "catbox")
    bad = tmp_path / "a.txt"
    bad.write_text("x")
    with pytest.raises(InputError, match="只支援"):
        up.upload_image(bad, "catbox")


def test_upload_session_is_dns_pinned_to_the_fixed_endpoint(monkeypatch):
    pinned = []

    class Sess:
        def close(self):
            pass

    monkeypatch.setattr(up.requests, "Session", Sess)
    monkeypatch.setattr(up, "_mount_pinning", lambda sess: pinned.append("mount"))
    monkeypatch.setattr(up, "_pin_session", lambda sess, url: pinned.append(url))
    sess = up._session_for("https://catbox.moe/user/api.php")
    assert pinned == ["mount", "https://catbox.moe/user/api.php"]
    sess.close()


def test_cancellable_reader_stops_before_sending_the_whole_file():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(FetchError) as exc:
        up._CancellableReader(io.BytesIO(b"data"), cancel).read(1)
    assert exc.value.detail == "cancelled"


def test_upload_enforces_the_host_size_limit(monkeypatch, tmp_path):
    host = up.HOSTS["catbox"]
    monkeypatch.setitem(up.HOSTS, "catbox", up.Host(host.key, host.label, host.endpoint, host.field,
                                                    dict(host.extra), 2, host.allowed_hosts, host.retention))
    with pytest.raises(InputError, match="上限"):
        up.upload_image(_png(tmp_path, data=b"12345"), "catbox")


def test_batch_continues_after_a_failure(monkeypatch, tmp_path):
    def fake(path, key, cancel=None):
        if str(path).endswith("bad.png"):
            raise FetchError("圖床忙碌。", "429")
        return up.UploadResult("ok.png", "https://files.catbox.moe/ok.png", key, 3)

    monkeypatch.setattr(up, "upload_image", fake)
    batch = up.upload_images([str(tmp_path / "bad.png"), str(tmp_path / "ok.png")], "catbox")
    assert len(batch.results) == 1 and len(batch.errors) == 1
    assert batch.errors[0][0] == "bad.png" and "忙碌" in batch.errors[0][1]


def test_cancelled_batch_stops_without_reporting_an_error(monkeypatch, tmp_path):
    cancel = threading.Event()

    def fake(path, key, cancel=None):
        cancel.set()
        raise FetchError("已取消圖片上傳。", "cancelled")

    monkeypatch.setattr(up, "upload_image", fake)
    batch = up.upload_images([str(tmp_path / "a.png"), str(tmp_path / "b.png")], "catbox", cancel=cancel)
    assert batch.results == [] and batch.errors == []
