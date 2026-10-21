import pytest

from conftest import pump, wait_until
from src.net.client import State
from src.net.session import Login, PttSession
from src.terminal.detect import Kind


@pytest.fixture
def sess(qapp):
    s = PttSession()
    notices = []
    s.notice.connect(notices.append)
    s.notices = notices
    yield s
    s.disconnect_()
    pump(50)


def connect(sess, bbs):
    sess.connect_to(bbs.url)
    assert wait_until(lambda: sess.client.state is State.CONNECTED)
    assert wait_until(lambda: sess.kind is Kind.LOGIN_PROMPT)


def test_connect_strips_proxy_prefix_and_sends_origin(sess, bbs_factory):
    bbs = bbs_factory()
    connect(sess, bbs)
    assert "HTTP/1.1" not in sess.screen.text()
    assert bbs.origin_seen == "https://term.ptt.cc"
    assert sess.login_state is Login.AT_LOGIN


def test_login_success_sends_credentials_once_then_main_menu(sess, bbs_factory):
    bbs = bbs_factory()
    connect(sess, bbs)
    assert sess.login("tester", "s3cret")
    assert wait_until(lambda: sess.login_state is Login.LOGGED_IN)
    assert bytes(bbs.received) == b"tester\rs3cret\r"          # exactly once, nothing else
    assert sess.logged_in and sess.kind is Kind.MAIN_MENU


def test_wrong_password_stops_without_retry(sess, bbs_factory):
    bbs = bbs_factory("badpass")
    connect(sess, bbs)
    sess.login("tester", "wrong")
    assert wait_until(lambda: sess.login_state is Login.FAILED)
    pump(600)
    assert bytes(bbs.received) == b"tester\rwrong\r"            # no second attempt
    assert not sess.logged_in


def test_duplicate_login_prompt_is_answered_no(sess, bbs_factory):
    bbs = bbs_factory("dup")
    connect(sess, bbs)
    sess.login("tester", "pw")
    assert wait_until(lambda: sess.login_state is Login.LOGGED_IN)
    assert bytes(bbs.received) == b"tester\rpw\rn\r"            # 'n' = never kick the other session


def test_press_any_key_is_handled(sess, bbs_factory):
    bbs = bbs_factory("anykey")
    connect(sess, bbs)
    sess.login("tester", "pw")
    assert wait_until(lambda: sess.login_state is Login.LOGGED_IN)
    assert bytes(bbs.received) == b"tester\rpw\r\r"


def test_unknown_screen_stops_and_tells_user(sess, bbs_factory):
    bbs = bbs_factory("weird")
    connect(sess, bbs)
    sess.login("tester", "pw")
    assert wait_until(lambda: sess.login_state is Login.MANUAL)
    n = len(bbs.received)
    pump(600)
    assert len(bbs.received) == n                               # nothing blindly sent afterwards
    assert any("手動" in m for m in sess.notices)


def test_login_refused_when_not_at_login_prompt(sess, bbs_factory):
    bbs = bbs_factory()
    connect(sess, bbs)
    bbs.goto("menu")
    assert wait_until(lambda: sess.kind is Kind.MAIN_MENU)
    assert not sess.login("tester", "pw")
    assert bytes(bbs.received) == b""


def test_login_refused_when_not_connected(sess):
    assert not sess.login("a", "b")


def test_password_never_reaches_the_log(sess, bbs_factory, tmp_path):
    import logging

    records = []

    class H(logging.Handler):
        def emit(self, r):
            records.append(r.getMessage())

    h = H()
    logging.getLogger("pttpost").addHandler(h)
    try:
        bbs = bbs_factory()
        connect(sess, bbs)
        sess.login("tester", "UNIQUE-PW-123")
        assert wait_until(lambda: sess.login_state is Login.LOGGED_IN)
    finally:
        logging.getLogger("pttpost").removeHandler(h)
    assert not any("UNIQUE-PW-123" in r for r in records)


def test_connection_loss_is_reported_not_retried(sess, bbs_factory):
    bbs = bbs_factory()
    connect(sess, bbs)
    sess.login("tester", "pw")
    assert wait_until(lambda: sess.logged_in)
    bbs.drop()
    assert wait_until(lambda: sess.client.state is State.DISCONNECTED)
    assert any("中斷" in m for m in sess.notices)
    pump(500)
    assert bbs.connections == 1 and not sess.logged_in


def test_connect_failure_reports_error(qapp):
    s = PttSession()
    notes = []
    s.notice.connect(notes.append)
    s.connect_to("ws://127.0.0.1:1/bbs")
    assert wait_until(lambda: bool(notes), 8000)
    assert s.client.state is State.DISCONNECTED


def test_cancel_while_connecting_is_not_undone_by_late_connected(qapp, bbs_factory):
    from conftest import pump, wait_until
    from src.net.client import State
    from src.net.session import PttSession
    bbs = bbs_factory()
    s = PttSession()
    s.connect_to(bbs.url)
    assert s.client.state is State.CONNECTING
    s.disconnect_()                                       # cancel before the handshake finishes
    pump(600)
    assert s.client.state is State.DISCONNECTED and not s.logged_in
    s.connect_to(bbs.url)                                 # a quick reconnect must not be hit by the old socket's signals
    assert wait_until(lambda: s.client.state is State.CONNECTED)
    s.disconnect_()
    pump(200)


def test_proxy_status_line_split_across_frames_is_stripped(qapp):
    from src.net.client import PttClient
    c = PttClient()
    got = []
    c.dataReceived.connect(got.append)
    c._on_message(b"HTTP/1.1 200 ")
    assert got == []                                       # still deciding
    c._on_message(b"OK\r\n\r\nhello")
    assert got == [b"hello"]
    c2 = PttClient()
    got2 = []
    c2.dataReceived.connect(got2.append)
    c2._on_message(b"plain")                               # no prefix at all: passed through untouched
    c2._on_message(b"HTTP/1.1 200 OK\r\n\r\n")             # a later frame is never treated as the proxy line
    assert got2 == [b"plain", b"HTTP/1.1 200 OK\r\n\r\n"]
