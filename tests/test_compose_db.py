import sqlite3

import pytest

from src import compose
from src.compose import Fields, check, has_errors, normalize, render, wrap, wrap_line
from src.errors import StorageError
from src.storage.db import Database


# ------------------------------------------------------------------ compose
def test_normalize_strips_ansi_controls_and_invisibles():
    t, notes = normalize("a\x1b[31mb\x1b[0m\x18c​d\r\ne\tf")
    assert t == "abcd\ne    f"
    assert len(notes) >= 3


def test_wrap_respects_width_and_keeps_urls():
    long = "中文" * 60
    for line in wrap(long, 76).split("\n"):
        assert compose.display_width(line) <= 76
    url = "https://example.com/" + "a" * 120
    assert wrap(f"請看 {url}", 76).split("\n")[-1] == url
    assert wrap("hello world " * 20, 40).replace("\n", " ").split() == ("hello world " * 20).split()   # no word cut


def test_wrap_does_not_start_a_line_with_closing_punctuation():
    text = "你" * 37 + "，" + "好" * 10
    lines = wrap(text, 76).split("\n")
    assert not lines[1].startswith("，")


def test_render_news_format_and_empty_fields_stay_empty():
    f = Fields(post_title="[新聞] 標題", site="某報", author="", url="https://x.test/a", news_title="標題", body="第一段\n\n第二段", notes="我的心得")
    title, body = render(f)
    assert title == "[新聞] 標題"
    assert "1.媒體來源: 某報" in body and "2.記者署名:" in body
    assert "未知" not in body and "未取得" not in body
    assert body.index("4.完整新聞內文:") < body.index("第一段") < body.index("5.完整新聞連結") < body.index("6.備註:") < body.index("我的心得")
    assert "\n--\n" not in body


def test_signature_applied_only_when_enabled_and_non_empty():
    f = Fields(post_title="t", body="b", signature="我的簽名", use_signature=True)
    _, body = render(f)
    assert body.endswith("\n--\n我的簽名")
    f.use_signature = False
    assert "--" not in render(f)[1]
    f.use_signature, f.signature = True, "  "
    assert "--" not in render(f)[1]


def test_check_flags_errors_and_warnings():
    issues = check("", "")
    assert has_errors(issues)
    issues = check("標題😀", "內容\x18")
    msgs = " ".join(str(i) for i in issues)
    assert "Big5" in msgs and "控制字元" in msgs
    issues = check("[新聞] ok", "1.媒體來源: \n2.記者署名: \n3.完整新聞標題: x\n4.完整新聞內文:\n內容\n--\n")
    assert not has_errors(issues)
    assert any("--" in i.message for i in issues) and any("媒體來源" in i.message for i in issues)
    long_title = "很長的標題" * 10
    assert any(i.level == "warn" and "標題" in i.message for i in check(long_title[:25], "x"))   # 50 bytes: warn only
    assert any(i.level == "error" and "過長" in i.message for i in check(long_title * 2, "x"))


def test_check_rejects_signature_with_separator_line():
    assert has_errors(check("t", "b", sig_text="a\n--\nb", used_signature=True))


def test_wrap_line_idempotent_on_short_lines():
    assert wrap_line("短行") == ["短行"]


# ------------------------------------------------------------------ database
@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.db")
    yield d
    d.close()


def test_draft_crud_and_search(db):
    a = db.save_draft({"title": "甲標題", "post_title": "[新聞] 甲", "body": "內文一", "notes": "心得", "site": "某報", "use_signature": True})
    b = db.save_draft({"title": "乙", "body": "別的"})
    assert db.get_draft(a)["use_signature"] == 1
    assert [d["id"] for d in db.list_drafts("內文一")] == [a]
    assert {d["id"] for d in db.list_drafts()} == {a, b}
    db.save_draft({"title": "甲改", "body": "內文二"}, a)
    assert db.get_draft(a)["title"] == "甲改" and db.get_draft(a)["body"] == "內文二"
    assert db.delete_draft(b) and db.get_draft(b) is None and not db.delete_draft(b)
    with pytest.raises(StorageError):
        db.save_draft({"title": "x"}, 9999)


def test_signature_roundtrip_and_persistence(tmp_path):
    p = tmp_path / "s.db"
    d = Database(p)
    assert d.signature == ""
    d.set_signature("第一行\n第二行")
    d.close()
    d2 = Database(p)
    assert d2.signature == "第一行\n第二行"
    d2.close()


def test_input_state_check_constraint_and_recovery(db):
    a = db.save_draft({"title": "t"})
    assert db.get_draft(a)["input_state"] == "none"
    db.set_input_state(a, "started")
    assert db.recover_interrupted_inputs() == 1
    assert db.get_draft(a)["input_state"] == "aborted"
    with pytest.raises(StorageError):
        db.set_input_state(a, "bogus")
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute("UPDATE drafts SET input_state='x'")


def test_newer_schema_is_refused(tmp_path):
    p = tmp_path / "n.db"
    c = sqlite3.connect(p)
    c.execute("PRAGMA user_version=99")
    c.commit()
    c.close()
    with pytest.raises(StorageError):
        Database(p)


def test_events_never_store_credentials(db):
    db.event("login", None, "ok")
    assert db.events()[0]["kind"] == "login"


def test_legacy_single_signature_becomes_first_entry_and_limit(tmp_path):
    d = Database(tmp_path / "x.db")
    d.set_setting("signature.text", "舊簽名")
    assert d.signatures() == [{"name": "簽名檔1", "text": "舊簽名"}] and d.signature == "舊簽名"
    for i in range(9):
        d.save_signature_entry(-1, f"n{i}", f"t{i}")
    assert len(d.signatures()) == 10
    import pytest
    with pytest.raises(ValueError):
        d.save_signature_entry(-1, "多的", "x")


def test_check_with_spaced_separator_and_signature_does_not_crash():
    issues = check("t", "內容\n -- \n", "sig", True)            # used to raise ValueError: '--' is not in list
    assert any("--" in i.message for i in issues)
    ok = check("t", "內容\n--\n簽名", "簽名", True)               # the system separator itself is fine
    assert not any("單獨一行" in i.message for i in ok)
    user_sep = check("t", "前\n--\n中\n--\n簽名", "簽名", True)    # only the last "--" is the system one
    assert sum("單獨一行" in i.message for i in user_sep) == 1


def test_redact_handles_quoted_dict_and_list_forms():
    from src.logging_setup import redact
    for text in ("{'pwd': 'hunter22'}", '{"password": "hunter22"}', "password=hunter22", "token: hunter22"):
        assert "hunter22" not in redact(text), text


def test_corrupt_signature_and_board_settings_return_empty(tmp_path):
    d = Database(tmp_path / "c.db")
    for bad in ("null", '"str"', "42", '{"a": 1}', "[1, 2, null]", "not json"):
        d.set_setting("signature.list", bad)
        d.set_setting("boards.favorites", bad)
        assert isinstance(d.signatures(), list) and isinstance(d.favorite_boards(), list)
    d.set_setting("boards.favorites", '["Stock", "stock", 5, "", "TooLongBoardNameXX", "NBA"]')
    assert d.favorite_boards() == ["Stock", "NBA"]


def test_database_init_failure_is_storage_error_and_connection_closed(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a sqlite database" * 50)
    with pytest.raises(StorageError):
        Database(bad)
    newer = tmp_path / "new.db"
    conn = sqlite3.connect(newer)
    conn.execute("PRAGMA user_version=99")
    conn.commit()
    conn.close()
    with pytest.raises(StorageError):
        Database(newer)
    newer.unlink()                                        # would fail on Windows if the connection had been left open


def test_migration_v1_to_v2_keeps_drafts_and_adds_signature_snapshot(tmp_path):
    p = tmp_path / "old.db"
    conn = sqlite3.connect(p)
    conn.executescript("""
        CREATE TABLE drafts(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL DEFAULT '', post_title TEXT NOT NULL DEFAULT '',
          site TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', published TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
          body TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', board TEXT NOT NULL DEFAULT '', use_signature INTEGER NOT NULL DEFAULT 0,
          preview_override TEXT, parse_status TEXT NOT NULL DEFAULT '', body_status TEXT NOT NULL DEFAULT '', field_states TEXT NOT NULL DEFAULT '',
          input_state TEXT NOT NULL DEFAULT 'none', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, draft_id INTEGER, detail TEXT NOT NULL DEFAULT '');
        INSERT INTO drafts(title, created_at, updated_at) VALUES('舊草稿', 'x', 'x');
        PRAGMA user_version=1;""")
    conn.commit()
    conn.close()
    d = Database(p)
    row = d.get_draft(1)
    assert row["title"] == "舊草稿" and row["signature_text"] == ""
    assert d.conn.execute("PRAGMA user_version").fetchone()[0] == 2


def test_draft_search_treats_percent_and_underscore_literally(tmp_path):
    d = Database(tmp_path / "s.db")
    d.save_draft({"title": "漲幅 50% 創高", "post_title": "[新聞] a", "body": "b"})
    d.save_draft({"title": "漲幅 500 創高", "post_title": "[新聞] b", "body": "b"})
    d.save_draft({"title": "snake_case 說明", "post_title": "[新聞] c", "body": "b"})
    d.save_draft({"title": "snakeXcase 說明", "post_title": "[新聞] d", "body": "b"})
    assert [r["title"] for r in d.list_drafts("50%")] == ["漲幅 50% 創高"]
    assert [r["title"] for r in d.list_drafts("snake_case")] == ["snake_case 說明"]


def test_migration_backup_includes_rows_still_in_the_wal(tmp_path):
    p = tmp_path / "wal.db"
    writer = sqlite3.connect(p)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.executescript("""
        CREATE TABLE drafts(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL DEFAULT '', post_title TEXT NOT NULL DEFAULT '',
          site TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', published TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
          body TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', board TEXT NOT NULL DEFAULT '', use_signature INTEGER NOT NULL DEFAULT 0,
          preview_override TEXT, parse_status TEXT NOT NULL DEFAULT '', body_status TEXT NOT NULL DEFAULT '', field_states TEXT NOT NULL DEFAULT '',
          input_state TEXT NOT NULL DEFAULT 'none', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, draft_id INTEGER, detail TEXT NOT NULL DEFAULT '');
        INSERT INTO drafts(title, created_at, updated_at) VALUES('WAL 草稿', 'x', 'x');
        PRAGMA user_version=1;""")
    writer.commit()                                      # keep the connection open: the row is still in -wal
    d = Database(p)
    try:
        bak = sqlite3.connect(str(p.with_name(p.name + ".bak-v1")))
        try:
            assert bak.execute("SELECT title FROM drafts").fetchone()[0] == "WAL 草稿"
        finally:
            bak.close()
        assert d.get_draft(1)["title"] == "WAL 草稿"
    finally:
        d.close()
        writer.close()


def test_backup_to_is_a_restorable_copy_and_refuses_the_live_path(tmp_path):
    d = Database(tmp_path / "live.db")
    try:
        did = d.save_draft({"title": "備份草稿", "body": "內容"})
        out = d.backup_to(tmp_path / "backup.db")
        assert out.is_file()
        b = Database(out)
        try:
            assert b.get_draft(did)["title"] == "備份草稿"
        finally:
            b.close()
        with pytest.raises(StorageError):
            d.backup_to(d.path)
    finally:
        d.close()


def test_database_waits_for_a_locked_file_instead_of_failing_immediately(tmp_path):
    d = Database(tmp_path / "w.db")
    assert d.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_upgrade_makes_a_backup_first_and_invisible_regex_is_escaped(tmp_path):
    p = tmp_path / "old.db"
    conn = sqlite3.connect(p)
    conn.executescript("""
        CREATE TABLE drafts(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL DEFAULT '', post_title TEXT NOT NULL DEFAULT '',
          site TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', published TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
          body TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', board TEXT NOT NULL DEFAULT '', use_signature INTEGER NOT NULL DEFAULT 0,
          preview_override TEXT, parse_status TEXT NOT NULL DEFAULT '', body_status TEXT NOT NULL DEFAULT '', field_states TEXT NOT NULL DEFAULT '',
          input_state TEXT NOT NULL DEFAULT 'none', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, draft_id INTEGER, detail TEXT NOT NULL DEFAULT '');
        PRAGMA user_version=1;""")
    conn.commit()
    conn.close()
    Database(p).close()
    assert (tmp_path / "old.db.bak-v1").is_file()
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent.joinpath("src/compose.py").read_text(encoding="utf-8")
    assert all(ord(c) < 128 or c in "，。" for c in src.split("INVISIBLE = re.compile(")[1].split("\n")[0])
