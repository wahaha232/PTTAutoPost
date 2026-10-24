import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.errors import FetchError, InputError
from src.parsers import fetch as F
from src.parsers.extract import FOUND, INFERRED, MISSING, find_image_urls, parse

PARA = "這是一段用來測試的新聞內文，包含足夠的字數以便判斷內文長度是否足夠。"
ARTICLE = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>測試新聞標題 | 某某新聞網</title>
<meta property="og:title" content="測試新聞標題 | 某某新聞網"><meta property="og:site_name" content="某某新聞網">
<meta name="author" content="某某新聞網">
<script type="application/ld+json">{{"@context":"https://schema.org","@graph":[{{"@type":"Organization","name":"某某新聞網"}},
{{"@type":"NewsArticle","headline":"測試新聞標題","datePublished":"2026-10-01T08:30:00+08:00",
"author":{{"@type":"Person","name":"王小明"}},"publisher":{{"@type":"Organization","name":"某某新聞網"}}}}]}}</script>
</head><body><nav><a href="/">首頁</a> <a href="/n">新聞</a></nav>
<article><h1>測試新聞標題</h1>{''.join(f'<p>{PARA}第{i}段。</p>' for i in range(6))}
<div class="related-news"><p>延伸閱讀：不要這個</p></div></article><footer>版權所有</footer></body></html>"""

SECOND = (ARTICLE.replace("測試新聞標題", "第二則新聞標題").replace("某某新聞網", "第二新聞網")
          .replace("王小明", "陳大華").replace(PARA + "第1段。", "第二篇獨有內容。"))


def test_generic_article_all_fields_found():
    r = parse(ARTICLE, "https://news.example/a/1")
    assert r.status == "success" and r.body_status == "likely_complete"
    assert r.title.value == "測試新聞標題" and r.title.status == FOUND          # site suffix stripped
    assert r.site.value == "某某新聞網"
    assert r.author.value == "王小明" and r.author.status == FOUND                # Person, not the Organization
    assert r.published.value.startswith("2026-10-01")
    assert "延伸閱讀" not in r.body.value and "首頁" not in r.body.value
    assert r.body.value.count("第") >= 6


def test_organization_author_is_not_taken_as_reporter_and_byline_is_inferred():
    html = ARTICLE.replace('"author":{"@type":"Person","name":"王小明"},', "").replace(
        "<article><h1>", "<article><h1>").replace(f"<p>{PARA}第0段。</p>", f"<p>（某社記者李大華台北1日電）{PARA}</p>")
    r = parse(html, "https://news.example/a/2")
    assert r.author.value == "李大華" and r.author.status == INFERRED
    assert any("推定" in w for w in r.warnings)


def test_missing_fields_are_marked_not_invented():
    html = "<html><body><div id='main'>" + "".join(f"<p>{PARA}</p>" for i in range(4)) + "</div></body></html>"
    r = parse(html, "https://x.example/p")
    assert r.title.status == MISSING and r.author.status == MISSING and r.published.status == MISSING
    assert r.status == "partial"
    assert any("未取得" in w for w in r.warnings)


def test_broken_jsonld_is_isolated():
    html = ARTICLE.replace('"headline":"測試新聞標題",', '"headline":"測試新聞標題", BROKEN')
    r = parse(html, "https://news.example/a/3")
    assert r.title.value == "測試新聞標題"
    assert any("JSON-LD" in w for w in r.warnings)


def test_title_only_is_not_success():
    html = '<html><head><meta property="og:title" content="只有標題"></head><body><p>短</p></body></html>'
    r = parse(html, "https://x.example/t")
    assert r.status == "partial" and r.body_status == "insufficient"


def test_truncation_marker_marks_body_suspect():
    html = ARTICLE.replace("</article>", "<p>展開全文</p></article>")
    r = parse(html, "https://news.example/a/4")
    assert r.body_status == "suspect_partial" and r.status == "partial"


def test_client_side_rendered_shell_is_reported_not_faked():
    html = '<html><head><title>App</title></head><body><div id="root"></div><noscript>You need to enable JavaScript</noscript></body></html>'
    r = parse(html, "https://spa.example/")
    assert r.page_class == "csr_shell" and r.status in ("failed", "partial")
    assert any("JavaScript" in w for w in r.warnings)


def test_login_wall_is_reported_without_bypass():
    html = "<html><head><title>會員專區</title></head><body><p>請登入後閱讀全文</p></body></html>"
    r = parse(html, "https://x.example/w")
    assert r.page_class == "login_wall" and r.status != "success"


def test_text_directly_in_div_is_extracted():
    inner = "<br>".join(f"{PARA}編號{i}" for i in range(5))
    html = f"<html><head><title>T</title></head><body><article><div id='c'>{inner}</div></article></body></html>"
    assert parse(html, "https://x.example/d").body.value.count("編號") == 5


def test_ptt_web_page():
    html = """<html><body><div id="main-content"><div class="article-metaline"><span class="article-meta-tag">作者</span><span class="article-meta-value">user (暱稱)</span></div>
<div class="article-metaline-right"><span class="article-meta-tag">看板</span><span class="article-meta-value">Test</span></div>
<div class="article-metaline"><span class="article-meta-tag">標題</span><span class="article-meta-value">[新聞] 測試</span></div>
<div class="article-metaline"><span class="article-meta-tag">時間</span><span class="article-meta-value">Wed Oct 14 14:14:07 2026</span></div>
第一行內文，這是 PTT 網頁版的文章。
第二行內文。
--
※ 發信站: 批踢踢實業坊(ptt.cc)
<div class="push"><span>推</span> 推文不應該出現</div></div></body></html>"""
    r = parse(html, "https://www.ptt.cc/bbs/Test/M.1.A.html")
    assert r.title.value == "[新聞] 測試" and r.author.value == "user" and r.site.value.startswith("PTT")
    assert "推文" not in r.body.value and "發信站" not in r.body.value and "第二行內文" in r.body.value


def test_article_inside_a_page_wide_form_is_still_extracted():
    paragraphs = "".join(
        f"<p>這是第 {i} 段完整的內文，包含足夠的字數與標點，用來確認表單容器不會被誤刪。</p>" for i in range(8))
    html = (f"<html><head><title>表單頁</title></head><body><form id='aspnetForm'>"
            f"<div class='article-content'>{paragraphs}</div></form></body></html>")
    r = parse(html, "https://x.example/form")
    assert "第 7 段" in (r.body.value or "")
    assert r.body_status == "likely_complete"


# ------------------------------------------------------------------ fetch (local server)
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = self.path
        if p == "/robots.txt":
            body = b"User-agent: *\nDisallow: /private\n"
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(body); return
        if p == "/ok":
            self._send(ARTICLE.encode("utf-8"), "text/html; charset=utf-8")
        elif p == "/second":
            self._send(SECOND.encode("utf-8"), "text/html; charset=utf-8")
        elif p == "/big5":
            page = "<html><head><title>大五碼測試</title></head><body><p>繁體中文內容：批踢踢實業坊。</p></body></html>"
            self._send(page.encode("cp950"), "text/html; charset=big5")
        elif p == "/meta-big5":
            page = '<html><head><meta charset="big5"><title>大五碼測試</title></head><body><p>繁體中文內容：批踢踢實業坊。</p></body></html>'
            self._send(page.encode("cp950"), "text/html")
        elif p == "/403":
            self._send(b"no", "text/html", 403)
        elif p == "/404":
            self._send(b"no", "text/html", 404)
        elif p == "/pdf":
            self._send(b"%PDF-1.4", "application/pdf")
        elif p == "/huge":
            self._send(b"<html>" + b"x" * 200000 + b"</html>", "text/html")
        elif p == "/slow":
            time.sleep(2.5)
            self._send(b"<html></html>", "text/html")
        elif p == "/loop":
            self.send_response(302); self.send_header("Location", "/loop"); self.end_headers()
        elif p.startswith("/private"):
            self._send(b"<html>private</html>", "text/html")
        else:
            self._send(b"nf", "text/html", 404)

    def _send(self, body, ctype, code=200):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url, **kw):
    kw.setdefault("min_interval", 0)
    return F.fetch(url, **kw)


def test_fetch_and_parse_end_to_end(server):
    f = get(server + "/ok")
    r = parse(f.html, f.final_url)
    assert f.status == 200 and f.charset == "utf-8" and r.status == "success"


def test_big5_is_decoded_from_header_and_from_meta(server):
    assert "批踢踢實業坊" in get(server + "/big5").html and get(server + "/big5").charset == "big5"
    f = get(server + "/meta-big5")
    assert "批踢踢實業坊" in f.html and f.charset == "big5"


@pytest.mark.parametrize("path,needle", [("/403", "存取被拒"), ("/404", "404"), ("/pdf", "不是網頁")])
def test_fetch_errors_are_explicit(server, path, needle):
    with pytest.raises(FetchError) as e:
        get(server + path)
    assert needle in str(e.value)


def test_restricted_pages_are_not_bypassed(server):
    with pytest.raises(FetchError) as e:
        get(server + "/403")
    assert "不會嘗試繞過" in str(e.value)


def test_size_limit_and_timeout_and_redirect_loop(server):
    with pytest.raises(FetchError, match="大小上限"):
        get(server + "/huge", max_bytes=1000)
    with pytest.raises(FetchError, match="逾時"):
        get(server + "/slow", timeout=1)
    with pytest.raises(FetchError, match="重新導向"):
        get(server + "/loop")


def test_robots_disallow_blocks_unless_overridden(server):
    with pytest.raises(FetchError, match="robots"):
        get(server + "/private/x")
    assert get(server + "/private/x", ignore_robots=True).status == 200


@pytest.mark.parametrize("bad", ["", "   ", "ftp://x.test/a", "javascript:alert(1)", "http://", "not a url", "http://[::1", "file:///etc/passwd"])
def test_invalid_urls_rejected_without_crash(bad):
    with pytest.raises(InputError):
        F.validate_url(bad)


def test_request_identifies_itself_honestly_and_sends_no_cookies(server):
    seen = {}

    class Spy(H):
        def do_GET(self):
            seen.update(self.headers)
            super().do_GET()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Spy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        get(f"http://127.0.0.1:{srv.server_address[1]}/ok")
    finally:
        srv.shutdown()
    assert "PTTAutoPost" in seen["User-Agent"] and "Mozilla" not in seen["User-Agent"]
    assert "Cookie" not in seen and "Referer" not in seen


# ------------------------------------------------------------------ media source / reporter fallbacks
def page(head="", body="", title="標題"):
    return f"<html><head><title>{title}</title>{head}</head><body>{body}</body></html>"


LONG = "".join(f"這是第{i}段新聞內文，用來提供足夠的字數讓內文判斷可以通過。" for i in range(8))


def test_site_falls_back_to_known_host_title_suffix_then_domain():
    r = parse(page(body=f"<article><p>{LONG}</p></article>"), "https://www.storm.mg/article/1")
    assert r.site.value == "風傳媒" and r.site.status == INFERRED and r.site.source == "host-map"
    r = parse(page(title="某則新聞 - 小報", body=f"<article><p>{LONG}</p></article>"), "https://unknown.example/a")
    assert r.site.value == "小報" and r.site.source == "title-suffix" and r.site.status == INFERRED
    r = parse(page(body=f"<article><p>{LONG}</p></article>"), "https://www.somewhere.example/a")
    assert r.site.value == "somewhere.example" and r.site.source == "domain"


def test_site_from_og_is_not_overridden_by_fallbacks():
    r = parse(page(head='<meta property="og:site_name" content="我的報社">', body=f"<article><p>{LONG}</p></article>"), "https://www.storm.mg/a")
    assert r.site.value == "我的報社" and r.site.status == FOUND


@pytest.mark.parametrize("snippet,expected,status", [
    ('<span class="author">周峻佑</span>', "周峻佑", FOUND),                                          # DOM author element
    ("<p>作者</p><p>蘇 子芸</p><p>|</p>", "蘇子芸", INFERRED),                                       # label / name / bar layout (technews style)
    ("<p>簡子喬｜Yahoo名人娛樂特派記者</p>", "簡子喬", INFERRED),                                      # name｜role
    ("<p>（中央社記者鄭維真彰化15日電）內文開始。</p>", "鄭維真", INFERRED),                           # place + 日電
    ("<p>（記者劉濱銓攝）</p>", "劉濱銓", INFERRED),                                                  # photo credit
    ("<p>文/ 王大明</p>", "王大明", INFERRED),
])
def test_reporter_detection_patterns(snippet, expected, status):
    r = parse(page(body=f"<article>{snippet}<p>{LONG}</p></article>"), "https://news.example/a")
    assert r.author.value == expected, (snippet, r.author)
    assert r.author.status == status


def test_jsonld_author_label_and_suffix_are_cleaned():
    ld = '<script type="application/ld+json">{"@type":"NewsArticle","headline":"T","author":{"@type":"Person","name":"編譯周辰陽／即時"}}</script>'
    assert parse(page(head=ld, body=f"<article><p>{LONG}</p></article>"), "https://news.example/a").author.value == "周辰陽"
    ld = ld.replace("編譯周辰陽／即時", "記者 林意筑 彰化報導")
    assert parse(page(head=ld, body=f"<article><p>{LONG}</p></article>"), "https://news.example/a").author.value == "林意筑"


def test_org_name_is_never_used_as_reporter():
    r = parse(page(head='<meta name="author" content="中央通訊社">', body=f"<article><p>{LONG}</p></article>"), "https://news.example/a")
    assert r.author.value is None and r.author.status == MISSING


def test_article_class_containing_promoted_is_not_thrown_away():
    html = page(body=f'<article class="node node-promoted node-sticky"><p>{LONG}</p></article>')
    assert len(parse(html, "https://news.example/a").body.value) > 200


def test_body_found_without_article_or_p_tags_and_with_css_in_js_class_names():
    junk = "".join(f'<div class="textButton__Box-sc-1 x{i}"><span>鈕</span></div>' for i in range(30))
    paras = "".join(f'<div class="Paragraph__Block-sc-9 a"><span>{LONG[i * 30:(i + 1) * 30 + 30]}</span></div>' for i in range(8))
    html = page(body=f'{junk}<div class="article-page__Body-sc-5"><div class="article-page__Content-sc-6">{paras}</div></div>')
    assert len(parse(html, "https://spa.example/a").body.value) > 150


def test_validate_url_rejects_userinfo_without_echoing_it():
    import pytest
    from src.errors import InputError
    from src.parsers.fetch import validate_url
    with pytest.raises(InputError) as e:
        validate_url("https://user:secret@news.example/a")
    assert "secret" not in str(e.value) and "secret" not in getattr(e.value, "detail", "")
    assert validate_url("https://news.example/a?x=1") == "https://news.example/a?x=1"


def test_parse_is_reentrant_time_note_does_not_leak_between_parses():
    future = "2999-01-01T00:00:00+00:00"
    html_bad = f"<html><head><title>甲</title><meta property='article:published_time' content='{future}'></head><body><article><p>{'內文很長。' * 40}</p></article></body></html>"
    html_ok = "<html><head><title>乙</title></head><body><article><p>" + "內文很長。" * 40 + "</p></article></body></html>"
    a = parse(html_bad, "https://a.example/1")
    b = parse(html_ok, "https://b.example/2")
    assert any("時區" in w for w in a.warnings) and not any("時區" in w for w in b.warnings)


def test_truncation_flag_does_not_leak_to_next_parse():
    cut = "<html><head><title>T</title></head><body><article>" + "<p>" + "完整的句子，內容很長。" * 30 + "</p><p>展開全文</p></article></body></html>"
    full = "<html><head><title>T2</title></head><body><article><p>" + "完整的句子，內容很長。" * 30 + "</p></article></body></html>"
    assert parse(cut, "https://x.example/1").body_status == "suspect_partial"
    assert parse(full, "https://x.example/2").body_status == "likely_complete"


def test_stream_read_error_becomes_fetch_error(monkeypatch):
    import pytest
    import requests
    from src.errors import FetchError
    from src.parsers import fetch as fm

    class Resp:
        url = "https://news.example/a"
        status_code = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def iter_content(self, _n):
            yield b"<html>"
            raise requests.exceptions.ChunkedEncodingError("connection broken")

        def close(self):
            pass

    monkeypatch.setattr(requests.Session, "get", lambda self, *a, **k: Resp())
    monkeypatch.setattr(fm, "_robots", lambda url, timeout: (True, "", None))
    with pytest.raises(FetchError) as e:
        fm.fetch("https://news.example/a", min_interval=0)
    assert "中斷" in e.value.message


# ---------------------------------------------------------------- SSRF / redirects / robots
class FakeResp:
    def __init__(self, status=200, headers=None, body=b"<html><body><article><p>" + "內文很長。".encode() * 60 + b"</p></article></body></html>"):
        self.status_code, self.url, self.body = status, "", body
        self.headers = {"Content-Type": "text/html; charset=utf-8", **(headers or {})}

    def iter_content(self, n):
        yield self.body

    def close(self):
        pass


def route(monkeypatch, table, robots=None):
    """requests.Session.get -> FakeResp per URL; records the URLs actually requested."""
    import requests
    seen = []

    def fake_get(self, url, **kw):
        seen.append(url)
        assert kw.get("allow_redirects") is False                  # redirects are followed by the program itself
        return table[url]
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(F, "_robots", robots or (lambda url, timeout: (True, "", None)))
    return seen


def test_ssrf_guard_blocks_loopback_private_and_metadata_hosts(monkeypatch):
    import socket
    monkeypatch.setattr(F, "ALLOW_PRIVATE_HOSTS", False)
    table = {"127.0.0.1": "127.0.0.1", "lan.example": "192.168.1.20", "meta.example": "169.254.169.254", "pub.example": "93.184.216.34"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, *a, **k: [(2, 1, 6, "", (table.get(h, h), 0))])
    for host in ("127.0.0.1", "lan.example", "meta.example"):
        with pytest.raises(FetchError) as e:
            F.fetch(f"http://{host}/x", min_interval=0)
        assert "本機或內網" in e.value.message
    seen = route(monkeypatch, {"http://pub.example/x": FakeResp()})
    assert F.fetch("http://pub.example/x", min_interval=0).status == 200 and seen == ["http://pub.example/x"]


def test_pinned_adapter_uses_the_pinned_ip_and_keeps_the_host_header(server):
    import requests
    from src.parsers.fetch import _PinnedAdapter
    port = int(server.rsplit(":", 1)[1])
    sess = requests.Session()
    sess.trust_env = False
    adapter = _PinnedAdapter()
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    try:
        adapter.pin("pinned.invalid", "127.0.0.1")       # the name cannot resolve; only the pin can connect
        r = sess.get(f"http://pinned.invalid:{port}/ok", timeout=5)
        assert r.status_code == 200 and "text/html" in r.headers.get("Content-Type", "")
    finally:
        sess.close()


def test_dns_failure_fails_closed_without_an_unpinned_request(monkeypatch):
    import requests
    import socket
    monkeypatch.setattr(F, "ALLOW_PRIVATE_HOSTS", False)

    def no_dns(*_a, **_k):
        raise socket.gaierror("temporary failure")
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)

    def must_not_request(*_a, **_k):
        raise AssertionError("a request was made without a validated, pinned address")
    monkeypatch.setattr(requests.Session, "get", must_not_request)
    with pytest.raises(FetchError) as e:
        F.fetch("http://rebind.example/x", min_interval=0)
    assert "DNS" in e.value.message


def test_redirect_to_internal_host_is_blocked_before_any_request(monkeypatch):
    import socket
    monkeypatch.setattr(F, "ALLOW_PRIVATE_HOSTS", False)
    table = {"pub.example": "93.184.216.34", "inner.example": "10.0.0.5"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, *a, **k: [(2, 1, 6, "", (table[h], 0))])
    seen = route(monkeypatch, {"http://pub.example/s": FakeResp(302, {"Location": "http://inner.example/admin"})})
    with pytest.raises(FetchError) as e:
        F.fetch("http://pub.example/s", min_interval=0)
    assert "本機或內網" in e.value.message and seen == ["http://pub.example/s"]       # inner host never requested


def test_redirect_rechecks_robots_for_new_host_and_warns(monkeypatch):
    asked = []

    def robots(url, timeout):
        asked.append(url)
        return (False if "blocked.example" in url else True), "", None
    route(monkeypatch, {"https://a.example/s": FakeResp(301, {"Location": "https://blocked.example/p"}),
                        "https://ok.example/s": FakeResp(301, {"Location": "https://b.example/p"}), "https://b.example/p": FakeResp()}, robots)
    with pytest.raises(FetchError) as e:
        F.fetch("https://a.example/s", min_interval=0)
    assert "robots" in e.value.detail and asked == ["https://a.example/s", "https://blocked.example/p"]
    r = F.fetch("https://ok.example/s", min_interval=0)
    assert any("b.example" in w for w in r.warnings) and r.final_url == "https://b.example/p"


def test_redirect_to_bad_scheme_userinfo_or_loop_is_refused(monkeypatch):
    route(monkeypatch, {"https://a.example/1": FakeResp(302, {"Location": "ftp://a.example/f"}),
                        "https://a.example/2": FakeResp(302, {"Location": "https://u:pw@a.example/x"}),
                        "https://a.example/3": FakeResp(302, {"Location": "/3"})})
    for path in ("1", "2", "3"):
        with pytest.raises(FetchError):
            F.fetch(f"https://a.example/{path}", min_interval=0)


def test_ignore_robots_does_not_request_robots_txt(monkeypatch):
    def boom(url, timeout):
        raise AssertionError("robots.txt must not be requested when ignored")
    route(monkeypatch, {"https://a.example/p": FakeResp()}, boom)
    assert F.fetch("https://a.example/p", ignore_robots=True, min_interval=0).status == 200


def test_oversized_robots_txt_is_not_read_forever(monkeypatch):
    import requests

    class Big(FakeResp):
        def iter_content(self, n):
            for _ in range(200):                                    # 200 x 16 KB >> limit
                yield b"#" * 16384
    monkeypatch.setattr(requests.Session, "get", lambda self, *a, **k: Big())
    F._robots_cache.pop("https://big.example", None)
    allowed, note, _delay = F._robots("https://big.example/x", 5)
    assert allowed is None and "robots" in note


def test_robots_failure_is_retried_after_its_short_ttl(monkeypatch):
    import requests
    monkeypatch.setattr(F, "_resolve_public", lambda url: None)      # no real DNS in this test
    monkeypatch.setattr(F, "ROBOTS_FAIL_TTL", 0)
    calls = []

    class R(FakeResp):
        pass

    def fake_get(self, url, **kw):
        calls.append(url)
        return R(503) if len(calls) == 1 else R(200, body=b"User-agent: *\nAllow: /\n")
    monkeypatch.setattr(requests.Session, "get", fake_get)
    F._robots_cache.pop("http://retry.example", None)
    assert F._robots("http://retry.example/a", 5)[0] is None          # transient 5xx: do not allow
    assert F._robots("http://retry.example/a", 5)[0] is True          # retried after the TTL, then allowed
    assert len(calls) == 2


def test_robots_txt_redirects_get_the_same_ssrf_checks(monkeypatch):
    import socket
    import requests
    monkeypatch.setattr(F, "ALLOW_PRIVATE_HOSTS", False)
    table = {"pub.example": "93.184.216.34", "lan.example": "192.168.0.9", "v6.example": "::1", "ll.example": "fe80::1"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, *a, **k: [(2, 1, 6, "", (table[h], 0))])
    for target in ("http://lan.example/robots.txt", "http://v6.example/robots.txt", "http://ll.example/robots.txt"):
        requested = []

        def fake_get(self, url, **kw):
            requested.append(url)
            assert kw.get("allow_redirects") is False
            return FakeResp(302, {"Location": target}) if url.startswith("http://pub.example") else FakeResp(200, body=b"User-agent: *\nAllow: /\n")
        monkeypatch.setattr(requests.Session, "get", fake_get)
        F._robots_cache.pop("http://pub.example", None)
        allowed, note, _d = F._robots("http://pub.example/a", 5)
        assert allowed is None and "robots" in note and requested == ["http://pub.example/robots.txt"]   # inner host never requested


def test_profile_lookup_uses_longest_domain_suffix(monkeypatch):
    from src.parsers import extract as E
    monkeypatch.setattr(E, "PROFILES", {"cna.com.tw": {"body": ["a"]}, "news.cna.com.tw": {"body": ["b"]}})
    assert E._profile_for("news.cna.com.tw")["body"] == ["b"]
    assert E._profile_for("www.cna.com.tw")["body"] == ["a"]
    assert E._profile_for("cna.com.tw")["body"] == ["a"]
    assert E._profile_for("na.com.tw") == {} and E._profile_for("evilcna.com.tw") == {}


def test_deeply_nested_jsonld_does_not_crash_the_parser():
    nested = "[" * 5000 + "]" * 5000
    html = f"<html><head><title>T</title><script type='application/ld+json'>{nested}</script></head><body><article><p>" + "內文很長。" * 60 + "</p></article></body></html>"
    assert parse(html, "https://x.example/n").body.value


def test_non_html_content_types_are_refused_and_user_agent_has_current_version(monkeypatch):
    from src.version import __version__
    assert __version__ in F.USER_AGENT
    for ctype in ("image/svg+xml", "application/rss+xml", "text/xml"):
        route(monkeypatch, {"https://a.example/x": FakeResp(200, {"Content-Type": ctype})})
        with pytest.raises(FetchError):
            F.fetch("https://a.example/x", min_interval=0)
    route(monkeypatch, {"https://a.example/x": FakeResp(200, {"Content-Type": "application/xhtml+xml"})})
    assert F.fetch("https://a.example/x", min_interval=0).status == 200


def test_find_image_urls_prefers_linked_original_and_picture_source():
    html = """<html><body><article>
    <a href="https://cdn.example.com/original.jpg"><img src="https://cdn.example.com/thumb.jpg"></a>
    <picture><source data-srcset="https://cdn.example.com/small.jpg 1x, https://cdn.example.com/large.jpg 2x">
    <img data-src="https://cdn.example.com/fallback.jpg"></picture>
    </article></body></html>"""
    assert find_image_urls(html, "https://news.example.com/a") == [
        "https://cdn.example.com/original.jpg", "https://cdn.example.com/large.jpg"]


def test_find_image_urls_upgrades_known_thumbnails_and_drops_ads():
    cna = """<html><body><article>
    <picture><source data-srcset="https://imgcdn.cna.com.tw/www/WebPhotos/400/20260101/x.jpg 1x,
    https://imgcdn.cna.com.tw/www/WebPhotos/800/20260101/x.jpg 2x">
    <img data-src="https://imgcdn.cna.com.tw/www/WebPhotos/400/20260101/x.jpg"></picture>
    <img src="https://imgcdn.cna.com.tw/www/website/img/ad300x223.jpg">
    <img src="https://www.cna.com.tw/logo.png">
    </article></body></html>"""
    assert find_image_urls(cna, "https://www.cna.com.tw/news/a/1.aspx") == [
        "https://imgcdn.cna.com.tw/www/WebPhotos/1024/20260101/x.jpg"]
    wiki = """<html><body><article>
    <a href="/wiki/File:Example.jpg"><img src="https://upload.wikimedia.org/wikipedia/commons/thumb/7/7a/Example.jpg/960px-Example.jpg"></a>
    </article></body></html>"""
    assert find_image_urls(wiki, "https://zh.wikipedia.org/wiki/X") == [
        "https://upload.wikimedia.org/wikipedia/commons/7/7a/Example.jpg"]


def test_find_image_urls_uses_img_sources_and_image_links_only():
    html = """<html><body><article>
    <img src="/a.jpg" width="800">
    <img data-src="https://cdn.example.com/b.png">
    <img src="data:image/gif;base64,AAAA">
    <img src="https://cdn.example.com/pixel.gif" width="1" height="1">
    <img src="https://cdn.example.com/c.svg">
    <img src="http://cdn.example.com/e.jpg">
    <img srcset="https://cdn.example.com/f.webp 1x, https://cdn.example.com/g.webp 2x">
    <a href="https://cdn.example.com/d.jpeg">d</a>
    <a href="https://cdn.example.com/page.html">no</a>
    </article></body></html>"""
    urls = find_image_urls(html, "https://news.example.com/story/1")
    assert urls == ["https://news.example.com/a.jpg", "https://cdn.example.com/b.png",
                    "https://cdn.example.com/g.webp", "https://cdn.example.com/d.jpeg"]
    assert find_image_urls(html, "https://news.example.com/", limit=1) == ["https://news.example.com/a.jpg"]


def test_find_image_urls_reads_bare_image_links_from_post_text():
    filler = "這是 PTT 貼文內文，包含足夠的字數讓內文判斷可以通過。" * 6
    html = f"""<html><body><article><div>{filler}<br>
    附圖：https://i.imgur.com/abc123.jpg。<br>
    另一張 https://imgur.com/xyz789<br>
    報導頁面：https://news.example.com/story/1<br>{filler}</div></article></body></html>"""
    assert find_image_urls(html, "https://www.ptt.cc/bbs/Test/M.1.A.html") == [
        "https://i.imgur.com/abc123.jpg", "https://imgur.com/xyz789"]
    assert parse(html, "https://www.ptt.cc/bbs/Test/M.1.A.html").images == [
        "https://i.imgur.com/abc123.jpg", "https://imgur.com/xyz789"]
