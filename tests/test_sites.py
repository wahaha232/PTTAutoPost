import pytest
from PySide6.QtWidgets import QMessageBox

from src import sites
from src.net.session import PttSession
from src.storage.db import Database
from src.ui.main_window import MainWindow


def test_default_sites_are_the_verified_list():
    items = sites.DEFAULT_SITES
    assert len(items) == 13
    assert items[0]["host"] == "ws.ptt.cc" and items[0]["protocol"] == "wss"
    assert items[1]["host"] == "ws.ptt2.cc"
    assert sum(1 for s in items if s["protocol"] == "telnet") == 8
    assert sum(1 for s in items if s["protocol"] == "ssh") == 3
    assert all(s["note"].startswith("2026-10-23") for s in items)
    assert sites.PROTOCOL_LABELS["telnet"] == "Telnet（明文）"


def test_site_address_and_validation():
    assert sites.site_address(sites.DEFAULT_SITES[0]) == "wss://ws.ptt.cc/bbs"
    assert sites.site_address(sites.DEFAULT_SITES[2]) == "telnet://bbs.ccns.ncku.edu.tw:23"
    assert sites.validate_site("x", "wss", "ws.ptt.cc", 443, "/bbs", "") is None
    assert sites.validate_site("", "wss", "ws.ptt.cc", 443, "/bbs", "")
    assert sites.validate_site("x", "gopher", "ws.ptt.cc", 443, "", "")
    assert sites.validate_site("x", "wss", "bad host", 443, "/bbs", "")
    assert sites.validate_site("x", "wss", "ws.ptt.cc", 0, "/bbs", "")
    assert sites.validate_site("x", "wss", "ws.ptt.cc", 443, "bbs", "")
    assert sites.validate_site("x", "telnet", "bbs.example", 23, "/path", "")


def test_database_defaults_roundtrip_and_empty_list(tmp_path):
    db = Database(tmp_path / "sites.db")
    assert len(db.site_bookmarks()) == 13
    items = db.site_bookmarks()
    items.pop()
    db.save_site_bookmarks(items)
    assert len(db.site_bookmarks()) == 12
    db.save_site_bookmarks([])
    assert db.site_bookmarks() == []
    db.close()


def test_check_site_uses_tcp_only(monkeypatch):
    class Sock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sites.socket, "create_connection", lambda addr, timeout: Sock())
    ok, msg = sites.check_site(sites.DEFAULT_SITES[2])
    assert ok and "TCP" in msg

    def fail(addr, timeout):
        raise OSError("no route")

    monkeypatch.setattr(sites.socket, "create_connection", fail)
    ok, msg = sites.check_site(sites.DEFAULT_SITES[2])
    assert not ok and "no route" in msg


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    db = Database(tmp_path / "sites-ui.db")
    window = MainWindow(db, PttSession())
    yield window
    window.session.disconnect_()
    db.close()


def test_sites_tab_shows_defaults_and_selection_fills_form(win):
    assert win.tabs.tabText(1) == "站台"
    assert win.site_list.count() == 13
    win.site_list.setCurrentRow(2)
    assert win.site_name.text() == "成大夢之大地"
    assert win.site_protocol.currentData() == "telnet"
    assert win.site_host.text() == "bbs.ccns.ncku.edu.tw"
    assert win.site_port.value() == 23


def test_add_save_delete_site_bookmarks_persist(win):
    win.site_name.setText("測試站")
    win.site_protocol.setCurrentIndex(win.site_protocol.findData("telnet"))
    win.site_host.setText("bbs.example.com")
    win.site_port.setValue(23)
    win.site_path.clear()
    win.site_note.setText("測試用")
    win.btn_site_add.click()
    assert win.site_list.count() == 14
    assert win.db.site_bookmarks()[-1]["name"] == "測試站"

    win.site_list.setCurrentRow(win.site_list.count() - 1)
    renamed = "\u6e2c\u8a66\u7ad9\u6539\u540d"
    win.site_name.setText(renamed)
    win.btn_site_save.click()
    assert win.db.site_bookmarks()[-1]["name"] == renamed

    win.btn_site_delete.click()                                # fixture answers Yes
    assert win.site_list.count() == 13
    assert all(s["name"] != renamed for s in win.db.site_bookmarks())


def test_duplicate_and_invalid_sites_are_rejected(win):
    before = win.site_list.count()
    site = win.db.site_bookmarks()[2]
    win.site_name.setText(site["name"])
    win.site_protocol.setCurrentIndex(win.site_protocol.findData(site["protocol"]))
    win.site_host.setText(site["host"])
    win.site_port.setValue(site["port"])
    win.site_path.setText(site["path"])
    win.btn_site_add.click()
    assert win.site_list.count() == before
    assert "相同" in win.lbl_site_test.text()

    win.site_name.setText("壞站")
    win.site_host.setText("bad host")
    win.btn_site_add.click()
    assert win.site_list.count() == before


def test_connect_wss_sets_endpoint_and_switches_tab(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win.session, "connect_to", lambda url, proxy=None: calls.append(url))
    win.session.client.state = __import__("src.net.client", fromlist=["State"]).State.DISCONNECTED
    win.site_list.setCurrentRow(0)
    win.btn_site_connect.click()
    assert calls == ["wss://ws.ptt.cc/bbs"]
    assert win.url_box.currentText() == "wss://ws.ptt.cc/bbs"
    assert win.tabs.currentIndex() == 0


def test_connect_telnet_is_supported_with_plaintext_warning(win, monkeypatch):
    calls = []
    notices = []
    warnings = []
    monkeypatch.setattr(win.session, "connect_to", lambda url, proxy=None: calls.append(url))
    monkeypatch.setattr(win, "_notice", lambda msg: notices.append(msg))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warnings.append(a[2]) or QMessageBox.StandardButton.Yes))
    win.site_list.setCurrentRow(2)
    win.btn_site_connect.click()
    assert calls == ["telnet://bbs.ccns.ncku.edu.tw:23"]
    assert warnings and "明文" in warnings[-1] and "帳號、密碼" in warnings[-1]
    assert win.url_box.currentText() == "telnet://bbs.ccns.ncku.edu.tw:23"


def test_telnet_connection_can_be_cancelled_at_the_warning(win, monkeypatch):
    calls = []
    notices = []
    monkeypatch.setattr(win.session, "connect_to", lambda url, proxy=None: calls.append(url))
    monkeypatch.setattr(win, "_notice", lambda msg: notices.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    win.site_list.setCurrentRow(2)
    win.btn_site_connect.click()
    assert calls == []
    assert notices and "取消" in notices[-1]


def test_connect_ssh_is_refused_but_bookmark_remains(win, monkeypatch):
    calls = []
    notices = []
    monkeypatch.setattr(win.session, "connect_to", lambda url, proxy=None: calls.append(url))
    monkeypatch.setattr(win, "_notice", lambda msg: notices.append(msg))
    win.site_list.setCurrentRow(10)
    win.btn_site_connect.click()
    assert calls == []
    assert notices and "SSH" in notices[-1]
    assert len(win.db.site_bookmarks()) == 13


def test_ipv6_hosts_are_bracketed_and_bad_ports_are_reported():
    site = {"name": "v6", "protocol": "telnet", "host": "2001:db8::1", "port": 23}
    assert sites.site_address(site) == "telnet://[2001:db8::1]:23"
    assert "連接埠" in sites.validate_site("x", "telnet", "bbs.example", "abc")
    assert sites.normalize_site({"name": "x", "protocol": "telnet", "host": "h", "port": "abc"})["port"] == 0
    ok, msg = sites.check_site({"host": "bad..host", "port": 23}, timeout=0.1)
    assert not ok and msg


def test_bbs_origin_follows_the_web_terminal_host():
    from src.net.client import origin_for
    assert origin_for("wss://ws.ptt.cc/bbs") == "https://term.ptt.cc"
    assert origin_for("wss://ws.ptt2.cc/bbs") == "https://term.ptt2.cc"          # 403 with term.ptt.cc
    assert origin_for("ws://127.0.0.1:1234/bbs") == "https://term.ptt.cc"
    assert origin_for("wss://bbs.example.org/ws") == "https://bbs.example.org"


def test_site_test_updates_status_without_blocking(win, monkeypatch):
    monkeypatch.setattr(sites, "check_site", lambda _site: (True, "TCP 可連線"))
    win.site_list.setCurrentRow(0)
    win.btn_site_test.click()
    from conftest import wait_until
    assert wait_until(lambda: "TCP" in win.lbl_site_test.text(), 3000)

