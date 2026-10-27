import pytest

from src.errors import FetchError
from src.net import image as img


class Resp:
    def __init__(self, body=b"\x89PNG", ctype="image/png", status=200, loc=None):
        self.status_code = status
        self.headers = {}
        if ctype is not None:
            self.headers["Content-Type"] = ctype
        if loc:
            self.headers["Location"] = loc
        self.body = body
        self.closed = False

    def close(self):
        self.closed = True

    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i:i + size]


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0)


def _fake(monkeypatch, *responses):
    sess = Session(responses)
    monkeypatch.setattr(img.requests, "Session", lambda: sess)
    monkeypatch.setattr(img, "_mount_pinning", lambda s: None)
    monkeypatch.setattr(img, "_pin_session", lambda s, url: None)
    return sess


@pytest.mark.parametrize("url", [
    "http://i.imgur.com/a.jpg",                    # plaintext
    "https://example.com/article",                 # no image extension, unknown host
    "https://i.imgur.com/a.svg",                   # SVG is never auto-opened
    "https://example.com/a.svg",
    "https://localhost/a.png",
    "https://192.168.1.1/a.png",
])
def test_rejects_urls_outside_the_image_policy(url):
    with pytest.raises(FetchError):
        img.fetch_image(url)


def test_article_mode_accepts_any_public_https_image(monkeypatch):
    _fake(monkeypatch, Resp(body=b"png", ctype="image/png"))
    data = img.fetch_image("https://cdn.example.com/image?id=1", strict_host=False)
    assert data.data == b"png"
    with pytest.raises(FetchError):
        img.fetch_image("http://cdn.example.com/image?id=1", strict_host=False)
    with pytest.raises(FetchError):
        img.fetch_image("https://cdn.example.com/image.svg", strict_host=False)


def test_returns_image_bytes_and_content_type(monkeypatch):
    sess = _fake(monkeypatch, Resp(body=b"png-bytes", ctype="image/png"))
    data = img.fetch_image("https://i.imgur.com/a.jpg")
    assert data.data == b"png-bytes" and data.content_type == "image/png"
    assert data.url == "https://i.imgur.com/a.jpg"
    assert sess.calls == ["https://i.imgur.com/a.jpg"]


def test_follows_a_redirect_to_another_known_host(monkeypatch):
    sess = _fake(monkeypatch,
                 Resp(status=302, ctype=None, loc="https://i.imgur.com/b.jpg"),
                 Resp(body=b"jpeg", ctype="image/jpeg"))
    data = img.fetch_image("https://imgur.com/a")
    assert data.url == "https://i.imgur.com/b.jpg" and data.data == b"jpeg"
    assert sess.calls == ["https://imgur.com/a", "https://i.imgur.com/b.jpg"]


@pytest.mark.parametrize("location", ["https://example.com/x.svg", "http://i.imgur.com/x.jpg",
                                      "https://localhost/x.jpg"])
def test_rejects_a_redirect_outside_the_image_policy(monkeypatch, location):
    _fake(monkeypatch, Resp(status=302, ctype=None, loc=location))
    with pytest.raises(FetchError, match="導向到不允許的網址"):
        img.fetch_image("https://i.imgur.com/a.jpg")


def test_rejects_too_many_redirects(monkeypatch):
    _fake(monkeypatch, *[Resp(status=302, ctype=None, loc="/loop") for _ in range(img.MAX_REDIRECTS + 2)])
    with pytest.raises(FetchError, match="重新導向次數過多"):
        img.fetch_image("https://i.imgur.com/a.jpg")


@pytest.mark.parametrize("ctype", ["text/html", "image/svg+xml", ""])
def test_rejects_non_image_content(monkeypatch, ctype):
    _fake(monkeypatch, Resp(body=b"<html>", ctype=ctype))
    with pytest.raises(FetchError, match="不是可顯示的圖片"):
        img.fetch_image("https://i.imgur.com/a.jpg")


def test_rejects_empty_bodies_and_oversize(monkeypatch):
    _fake(monkeypatch, Resp(body=b"", ctype="image/png"))
    with pytest.raises(FetchError, match="空的"):
        img.fetch_image("https://i.imgur.com/a.jpg")
    _fake(monkeypatch, Resp(body=b"0123456789", ctype="image/png"))
    with pytest.raises(FetchError, match="大小上限"):
        img.fetch_image("https://i.imgur.com/a.jpg", max_bytes=4)


@pytest.mark.parametrize("status,needle", [(403, "拒絕存取"), (404, "HTTP 404")])
def test_http_errors_are_explicit(monkeypatch, status, needle):
    _fake(monkeypatch, Resp(body=b"no", ctype="image/png", status=status))
    with pytest.raises(FetchError, match=needle):
        img.fetch_image("https://i.imgur.com/a.jpg")


def test_cancellation_stops_the_download(monkeypatch):
    import threading
    _fake(monkeypatch, Resp(body=b"x" * 200_000, ctype="image/png"))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(FetchError, match="已取消"):
        img.fetch_image("https://i.imgur.com/a.jpg", cancel=cancel)


def test_zip_download_keeps_original_bytes_and_unique_names(monkeypatch, tmp_path):
    import zipfile
    data = b"\x89PNG-original-bytes"
    monkeypatch.setattr(img, "fetch_image",
                        lambda url, **kw: img.ImageData(url, "image/png", data))
    target = tmp_path / "images.zip"
    result = img.download_images_zip(
        ["https://cdn.example.com/a.jpg", "https://cdn.example.com/sub/a.jpg",
         "https://cdn.example.com/noext"], target)
    assert result.saved == 3 and result.skipped == 0 and result.total_bytes == len(data) * 3
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
        assert names == ["a.jpg", "a-2.jpg", "noext.png"]
        assert all(zf.read(name) == data for name in names)
    assert not target.with_name(target.name + ".part").exists()


def test_zip_download_skips_failed_images_and_reports_them(monkeypatch, tmp_path):
    calls = []

    def fake(url, **kw):
        calls.append(url)
        if "bad" in url:
            raise FetchError("圖片連線逾時。", "timeout")
        return img.ImageData(url, "image/jpeg", b"jpeg")

    monkeypatch.setattr(img, "fetch_image", fake)
    result = img.download_images_zip(
        ["https://cdn.example.com/bad.jpg", "https://cdn.example.com/ok.jpg"], tmp_path / "i.zip")
    assert result.saved == 1 and result.skipped == 1 and "bad.jpg" in result.errors[0]
    assert calls == ["https://cdn.example.com/bad.jpg", "https://cdn.example.com/ok.jpg"]


def test_zip_download_removes_the_partial_file_when_nothing_works(monkeypatch, tmp_path):
    def fake(url, **kw):
        raise FetchError("not an image", "type")

    monkeypatch.setattr(img, "fetch_image", fake)
    target = tmp_path / "empty.zip"
    with pytest.raises(FetchError, match="沒有任何圖片"):
        img.download_images_zip(["https://cdn.example.com/a.jpg"], target)
    assert not target.exists() and not target.with_name(target.name + ".part").exists()


def test_referer_is_per_request_and_never_follows_a_redirect_to_another_host(monkeypatch):
    seen = []

    class Spy(Session):
        def get(self, url, **kwargs):
            seen.append((url, dict(kwargs.get("headers") or {})))
            return super().get(url, **kwargs)
    sess = Spy([Resp(status=302, ctype=None, loc="https://other.example/b.jpg"), Resp(body=b"jpeg", ctype="image/jpeg")])
    monkeypatch.setattr(img.requests, "Session", lambda: sess)
    monkeypatch.setattr(img, "_mount_pinning", lambda s: None)
    monkeypatch.setattr(img, "_pin_session", lambda s, url: None)
    img.fetch_image("https://cdn.news.example/a.jpg", strict_host=False, referer="https://news.example/story/1?x=2")
    assert "Referer" not in sess.headers                               # never session-wide
    assert seen[0] == ("https://cdn.news.example/a.jpg", {"Referer": "https://news.example/"})   # origin only
    assert seen[1] == ("https://other.example/b.jpg", {})              # redirect to another host: dropped
    seen.clear()
    sess.responses = [Resp(body=b"png", ctype="image/png")]
    img.fetch_image("https://news.example/img/a.png", strict_host=False, referer="https://news.example/story/1")
    assert seen[0][1] == {"Referer": "https://news.example/story/1"}  # the article's own host: full URL


@pytest.mark.parametrize("location", ["https://[bad/x.jpg", "https://i.imgur.com:99999/x.jpg"])
def test_malformed_redirect_location_is_a_fetch_error(monkeypatch, location):
    _fake(monkeypatch, Resp(status=302, ctype=None, loc=location))
    with pytest.raises(FetchError, match="導向到不允許的網址"):
        img.fetch_image("https://i.imgur.com/a.jpg")
