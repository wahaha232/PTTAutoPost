from src import conn_history as ch


def test_add_puts_most_recent_first_without_duplicates():
    h = ch.add([], "wss://ws.ptt.cc/bbs")
    h = ch.add(h, "telnet://bbs.gamer.com.tw:23")
    h = ch.add(h, "wss://ws.ptt.cc/bbs")
    assert h == ["wss://ws.ptt.cc/bbs", "telnet://bbs.gamer.com.tw:23"]


def test_add_keeps_at_most_ten():
    h: list[str] = []
    for i in range(15):
        h = ch.add(h, f"telnet://bbs{i}.example:23")
    assert len(h) == ch.MAX_ENTRIES and h[0] == "telnet://bbs14.example:23" and h[-1] == "telnet://bbs5.example:23"


def test_refused_or_credential_bearing_endpoints_are_never_recorded():
    for bad in ("", "   ", "ftp://x", "wss://u:p@ws.ptt.cc/bbs", "ssh://bbs:pw@ptt.cc:22", "http://ws.ptt.cc/bbs"):
        assert ch.add(["wss://ws.ptt.cc/bbs"], bad) == ["wss://ws.ptt.cc/bbs"], bad


def test_parse_and_dump_round_trip_and_survive_bad_data():
    h = ["telnet://bbs.gamer.com.tw:23", "ssh://bbs@ptt.cc:22"]
    assert ch.parse(ch.dump(h)) == h
    for raw in ("", "not json", "{}", "123", '["ftp://x", 5, null, "wss://ws.ptt.cc/bbs"]'):
        assert ch.parse(raw) in ([], ["wss://ws.ptt.cc/bbs"]), raw


def test_main_window_records_on_connect_and_clears(qapp, bbs_factory, tmp_path):
    from conftest import wait_until
    from src.net.client import DEFAULT_URL, State
    from src.net.session import PttSession
    from src.storage.db import Database
    from src.ui.main_window import MainWindow

    path = tmp_path / "history.db"
    db = Database(path)
    win = MainWindow(db, PttSession())
    items = lambda w: [w.url_box.itemText(i) for i in range(w.url_box.count())]
    assert items(win) == [DEFAULT_URL] and not win.btn_clear_history.isEnabled()
    bbs = bbs_factory()
    win.session.connect_to(bbs.url)
    assert wait_until(lambda: win.session.client.state is State.CONNECTED)
    assert wait_until(lambda: items(win) == [bbs.url, DEFAULT_URL])
    assert win.btn_clear_history.isEnabled() and "1 筆" in win.lbl_history.text()
    win.session.disconnect_()
    db.close()

    db2 = Database(path)                                   # remembered across restarts
    win2 = MainWindow(db2, PttSession())
    assert items(win2) == [bbs.url, DEFAULT_URL]
    win2.url_box.setEditText("telnet://typed.example:23")
    win2.btn_clear_history.click()
    assert items(win2) == [DEFAULT_URL] and win2.url_box.currentText() == "telnet://typed.example:23"
    assert ch.parse(db2.get_setting(ch.SETTING_KEY, "[]")) == []
    db2.close()
