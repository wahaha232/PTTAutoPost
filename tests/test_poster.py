import pytest

from conftest import pump, wait_until
from src.net.client import State
from src.net.poster import PostTyper, Target, build_chunks, encode_big5, preflight
from src.net.session import PttSession
from src.terminal.detect import Kind

BODY = "第一行：中文與ＡＢＣ，全形標點！\n\n第三行 http://example.com/a?b=1\n最後一行"


@pytest.fixture
def rig(qapp, bbs_factory):
    bbs = bbs_factory()
    sess = PttSession()
    typer = PostTyper(sess)
    done = []
    typer.finished.connect(lambda ok, msg: done.append((ok, msg)))
    sess.connect_to(bbs.url)
    assert wait_until(lambda: sess.kind is Kind.LOGIN_PROMPT)
    assert sess.login("tester", "pw")
    assert wait_until(lambda: sess.logged_in)
    yield bbs, sess, typer, done
    sess.disconnect_()
    pump(50)


def goto(bbs, sess, state, kind):
    bbs.goto(state)
    assert wait_until(lambda: sess.kind is kind)


FORBIDDEN = (b"\x18", b"\x11", b"\x1b", b"\x1a", b"\x03")


def test_types_title_exactly_and_sends_no_enter(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "title", Kind.TITLE_PROMPT)
    assert typer.start(Target.TITLE, "[新聞] 測試標題ＡＢＣ") is None
    assert wait_until(lambda: bool(done))
    assert done[0][0] is True
    assert bytes(bbs.after_login) == "[新聞] 測試標題ＡＢＣ".encode("cp950")
    assert b"\r" not in bbs.after_login          # the user presses Enter, never us
    assert bbs.state == "title"                   # still waiting at the title prompt


def test_types_body_exactly_and_stops_before_save(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "editor", Kind.EDITOR)
    assert typer.start(Target.BODY, BODY) is None
    assert wait_until(lambda: bool(done), 8000)
    assert done[0][0] is True, done
    assert bytes(bbs.after_login) == BODY.replace("\n", "\r").encode("cp950")
    for f in FORBIDDEN:
        assert f not in bbs.after_login
    assert bbs.state == "editor"                  # never left the editor, never saved
    assert "存檔" in done[0][1]


def test_long_body_is_chunked_without_splitting_characters(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "editor", Kind.EDITOR)
    text = "\n".join("這是第%d行，" % i + "測試" * 15 for i in range(12))
    chunks = build_chunks(text)
    assert all(len(c) <= 100 for c in chunks) and len(chunks) > 5
    assert b"".join(chunks) == text.replace("\n", "\r").encode("cp950")
    assert typer.start(Target.BODY, text) is None
    assert wait_until(lambda: bool(done), 15000)
    assert done[0][0] is True, done
    assert bytes(bbs.after_login) == text.replace("\n", "\r").encode("cp950")


def test_refuses_on_wrong_screen_with_zero_bytes(rig):
    bbs, sess, typer, done = rig
    assert sess.kind is Kind.MAIN_MENU
    assert "編輯畫面" in typer.start(Target.BODY, "hello")
    assert "標題" in typer.start(Target.TITLE, "hello")
    pump(300)
    assert bytes(bbs.after_login) == b"" and not done


def test_refuses_when_not_logged_in(qapp, bbs_factory):
    bbs = bbs_factory()
    sess = PttSession()
    typer = PostTyper(sess)
    sess.connect_to(bbs.url)
    assert wait_until(lambda: sess.kind is Kind.LOGIN_PROMPT)
    assert "登入" in typer.start(Target.BODY, "hello")
    assert bytes(bbs.received) == b""
    sess.disconnect_()
    pump(50)


@pytest.mark.parametrize("bad", ["含emoji😀", "含\x18控制字元", "含\x1b[31m跳脫", "簡体字：这个"])
def test_refuses_unsafe_or_unencodable_text(rig, bad):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "editor", Kind.EDITOR)
    why = typer.start(Target.BODY, bad)
    assert why is not None
    pump(200)
    assert bytes(bbs.after_login) == b""


def test_title_with_newline_refused(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "title", Kind.TITLE_PROMPT)
    assert typer.start(Target.TITLE, "a\nb") is not None


def test_second_typing_into_non_empty_editor_is_refused(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "editor", Kind.EDITOR)
    assert typer.start(Target.BODY, "第一次輸入") is None
    assert wait_until(lambda: bool(done))
    sent = len(bbs.after_login)
    why = typer.start(Target.BODY, "第一次輸入")
    assert why and "不是空的" in why
    pump(200)
    assert len(bbs.after_login) == sent           # nothing re-typed


def test_connection_drop_mid_typing_aborts_and_never_resends(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "editor", Kind.EDITOR)
    text = "\n".join("行%d " % i + "測試內容" * 10 for i in range(15))
    typer.progress.connect(lambda i, n: bbs.drop() if i == 2 else None)
    assert typer.start(Target.BODY, text) is None
    assert wait_until(lambda: bool(done), 8000)
    assert done[0][0] is False and "中斷" in done[0][1]
    got = bytes(bbs.after_login)
    assert 0 < len(got) < len(text.replace("\n", "\r").encode("cp950"))
    assert text.replace("\n", "\r").encode("cp950").startswith(got)       # a clean prefix, nothing duplicated
    n = len(bbs.received)
    pump(600)
    assert len(bbs.received) == n and bbs.connections == 1 and sess.client.state is State.DISCONNECTED


def test_unexpected_screen_mid_typing_aborts(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "editor", Kind.EDITOR)
    text = "\n".join("行%d " % i + "測試內容" * 10 for i in range(15))

    def leave(i, n):
        if i == 2:
            bbs.push(b"\x1b[2J\x1b[H" + "【主功能表】".encode("cp950"))
    typer.progress.connect(leave)
    assert typer.start(Target.BODY, text) is None
    assert wait_until(lambda: bool(done), 8000)
    assert done[0][0] is False and "畫面" in done[0][1]


def test_cancel_stops_further_chunks(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "editor", Kind.EDITOR)
    text = "\n".join("行%d " % i + "測試內容" * 10 for i in range(15))
    typer.progress.connect(lambda i, n: typer.cancel() if i == 3 else None)
    assert typer.start(Target.BODY, text) is None
    assert wait_until(lambda: bool(done), 8000)
    assert done[0][0] is False and "取消" in done[0][1]
    pump(300)                                   # let the chunk that was already in flight reach the server
    n = len(bbs.after_login)
    pump(500)
    assert len(bbs.after_login) == n


def test_started_signal_fires_before_first_byte(rig):
    bbs, sess, typer, done = rig
    goto(bbs, sess, "editor", Kind.EDITOR)
    seen = []
    typer.started.connect(lambda t: seen.append(len(bbs.after_login)))
    assert typer.start(Target.BODY, "hello") is None
    assert wait_until(lambda: bool(done))
    assert seen == [0]


def test_encode_big5_reports_positions():
    data, bad = encode_big5("ab😀c")
    assert data is None and bad == [(2, "😀")]


def test_title_typing_stops_when_screen_leaves_title_prompt_mid_way(rig, monkeypatch):
    import src.net.poster as P
    bbs, sess, typer, done = rig
    goto(bbs, sess, "title", Kind.TITLE_PROMPT)
    real_build = P.build_chunks
    monkeypatch.setattr(P, "build_chunks", lambda text, limit=6: real_build(text, 6))
    sent = []
    orig = sess.client.send

    def spy(data):
        ok = orig(data)
        if ok:
            sent.append(bytes(data))
            if len(sent) == 1:                        # right after the first chunk the screen jumps to the main menu
                bbs.goto("menu")
        return ok
    monkeypatch.setattr(sess.client, "send", spy)
    assert typer.start(Target.TITLE, "[新聞] 一個比較長的測試標題用來分段") is None
    assert wait_until(lambda: bool(done), 8000)
    assert done[0][0] is False and len(sent) == 1       # aborted: no further chunk went out


def test_preflight_refuses_while_pasting(qapp):
    why = preflight(PttSession(), Target.BODY, "hello", pasting=True)
    assert why and "\u8cbc\u4e0a\u9032\u884c\u4e2d" in why


def test_shared_send_lock_blocks_typing_while_paste_owns_the_stream(qapp):
    from src.net.sendlock import PASTE
    sess = PttSession()
    assert sess.send_lock.acquire(PASTE)
    try:
        why = preflight(sess, Target.BODY, "hello")
        assert why and "\u8cbc\u4e0a" in why
        typer = PostTyper(sess)
        assert typer.start(Target.BODY, "hello")
        assert not typer.running and typer.bytes_sent == 0
    finally:
        sess.send_lock.release(PASTE)
    assert preflight(sess, Target.BODY, "hello") is not None          # now refused for being offline, not for pasting
