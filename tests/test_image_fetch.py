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
