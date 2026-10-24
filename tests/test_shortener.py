import pytest

from src.errors import FetchError, InputError
from src.net import shortener as sh


class Resp:
    def __init__(self, status=200, text="https://is.gd/abc"):
        self.status_code, self.text = status, text


class Sess:
    def __init__(self, resp):
        self.resp, self.kwargs = resp, None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return self.resp

    def post(self, url, **kwargs):
        self.kwargs = kwargs
        return self.resp


def _patch(monkeypatch, resp):
    fake = Sess(resp)
    monkeypatch.setattr(sh, "_session_for", lambda url: fake)
    return fake


def test_isgd_shortens_with_encoded_url(monkeypatch):
    fake = _patch(monkeypatch, Resp(text="https://is.gd/abc"))
    assert sh.shorten_url("isgd", "https://example.com/a?b=1") == "https://is.gd/abc"
    assert fake.kwargs["params"] == {"url": "https://example.com/a?b=1"}
    assert fake.kwargs["allow_redirects"] is False


def test_cleanuri_posts_json(monkeypatch):
    fake = _patch(monkeypatch, Resp(text='{"result_url":"https://cleanuri.com/x"}'))
    assert sh.shorten_url("cleanuri", "https://example.com/a") == "https://cleanuri.com/x"
    assert fake.kwargs["json"] == {"url": "https://example.com/a"}


def test_rejects_an_unexpected_response_host(monkeypatch):
    _patch(monkeypatch, Resp(text="https://evil.example/x"))
    with pytest.raises(FetchError, match="非預期"):
        sh.shorten_url("isgd", "https://example.com/a")


def test_rejects_invalid_input_before_any_request(monkeypatch):
    called = []
    monkeypatch.setattr(sh, "_session_for", lambda url: called.append(url))
    with pytest.raises(InputError):
        sh.shorten_url("isgd", "javascript:alert(1)")
    assert called == []


def test_reports_http_error(monkeypatch):
    _patch(monkeypatch, Resp(status=429, text="slow down"))
    with pytest.raises(FetchError, match="429"):
        sh.shorten_url("tinyurl", "https://example.com/a")
