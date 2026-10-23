from src.links import Link, find_links, is_image_url, validate_http_url
from src.terminal.screen import Screen


def make_screen(text: str) -> Screen:
    s = Screen()
    s.feed(text.encode("cp950"))
    return s


def test_finds_url_and_maps_cells_after_double_width_text():
    s = make_screen("中文 https://example.com/a")
    links = find_links(s)
    assert len(links) == 1
    link = links[0]
    assert link.url == "https://example.com/a"
    assert (link.row, link.start_col) == (0, 5)
    assert link.end_col - link.start_col == len(link.url)
    assert link.contains(0, 5) and link.contains(0, 25)
    assert not link.contains(0, 26)


def test_finds_url_immediately_after_chinese_text():
    s = make_screen("中文https://example.com/a")
    link = find_links(s)[0]
    assert link.start_col == 4
    assert link.url == "https://example.com/a"


def test_multiple_links_on_one_row_and_trailing_punctuation():
    s = make_screen("A https://a.example/x, B http://b.example/y。")
    links = find_links(s)
    assert [x.url for x in links] == ["https://a.example/x", "http://b.example/y"]
    assert links[0].end_col - links[0].start_col == len(links[0].url)
    assert links[1].end_col - links[1].start_col == len(links[1].url)


def test_does_not_join_wrapped_urls():
    s = make_screen("https://example.com/very\r\nlong/path")
    links = find_links(s)
    assert [x.url for x in links] == ["https://example.com/very"]
    assert all("long/path" not in x.url for x in links)


def test_rejects_other_schemes_userinfo_and_control_characters():
    for text in ("ftp://example.com/a", "file:///tmp/a", "javascript:alert(1)", "data:text/plain,x"):
        assert find_links(make_screen(text)) == []
    assert find_links(make_screen("http://user:pass@example.com/a")) == []
    assert not validate_http_url("http://example.com/\x01")
    assert not validate_http_url("http:///nohost")
    assert validate_http_url("https://example.com/a?b=1#c")


def test_image_urls():
    for url in ("https://i.imgur.com/a.jpg", "https://imgur.com/abc", "https://example.com/pic.PNG?x=1",
                "https://i.ibb.co/x/y.webp"):
        assert is_image_url(url), url
    for url in ("https://example.com/article", "https://notimgur.com/article", "https://example.com/pic"):
        assert not is_image_url(url), url


def test_link_contains_uses_cell_columns():
    link = Link("https://example.com", 2, 10, 29)
    assert link.contains(2, 10) and link.contains(2, 28)
    assert not link.contains(2, 9) and not link.contains(3, 10)
