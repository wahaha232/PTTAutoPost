"""Local SQLite storage: drafts, global signature, settings, event log. No credentials, ever."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..errors import StorageError
from ..logging_setup import get_logger
from ..paths import data_dir

log = get_logger("db")
SCHEMA_VERSION = 1
MAX_SIGNATURES = 10

DRAFT_FIELDS = ("title", "post_title", "site", "author", "published", "url", "body", "notes", "board",
                "use_signature", "preview_override", "parse_status", "body_status", "field_states", "input_state")
INPUT_STATES = ("none", "started", "done", "aborted")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else data_dir() / "pttpost.db"
        try:
            self.conn = sqlite3.connect(str(self.path))
        except sqlite3.Error as e:
            raise StorageError("無法開啟資料庫。", str(e)) from e
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        v = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if v > SCHEMA_VERSION:
            raise StorageError("資料庫版本比程式新，請使用較新的程式版本。", f"db={v} app={SCHEMA_VERSION}")
        if v < 1:
            with self.conn:
                self.conn.executescript("""
                CREATE TABLE drafts(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL DEFAULT '', post_title TEXT NOT NULL DEFAULT '',
                  site TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', published TEXT NOT NULL DEFAULT '',
                  url TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                  board TEXT NOT NULL DEFAULT '', use_signature INTEGER NOT NULL DEFAULT 0,
                  preview_override TEXT, parse_status TEXT NOT NULL DEFAULT '', body_status TEXT NOT NULL DEFAULT '',
                  field_states TEXT NOT NULL DEFAULT '',
                  input_state TEXT NOT NULL DEFAULT 'none' CHECK(input_state IN ('none','started','done','aborted')),
                  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL,
                                    draft_id INTEGER, detail TEXT NOT NULL DEFAULT '');
                CREATE INDEX idx_drafts_updated ON drafts(updated_at DESC);
                PRAGMA user_version=1;""")

    # ---------------------------------------------------------------- drafts
    def save_draft(self, data: dict, draft_id: int | None = None) -> int:
        vals = {k: data.get(k, "") for k in DRAFT_FIELDS if k not in ("use_signature", "input_state", "preview_override")}
        vals["use_signature"] = 1 if data.get("use_signature") else 0
        vals["preview_override"] = data.get("preview_override") or None
        ts = now()
        try:
            with self.conn:
                if draft_id is None:
                    cols = list(vals) + ["created_at", "updated_at"]
                    cur = self.conn.execute(f"INSERT INTO drafts({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                                            [*vals.values(), ts, ts])
                    return int(cur.lastrowid)
                sets = ",".join(f"{k}=?" for k in vals) + ",updated_at=?"
                cur = self.conn.execute(f"UPDATE drafts SET {sets} WHERE id=?", [*vals.values(), ts, draft_id])
                if cur.rowcount == 0:
                    raise StorageError("找不到要更新的草稿。")
                return draft_id
        except sqlite3.Error as e:
            raise StorageError("儲存草稿失敗。", str(e)) from e

    def get_draft(self, draft_id: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return dict(r) if r else None

    def list_drafts(self, query: str = "") -> list[dict]:
        if query.strip():
            like = f"%{query.strip()}%"
            rows = self.conn.execute(
                "SELECT * FROM drafts WHERE title LIKE ? OR post_title LIKE ? OR body LIKE ? OR notes LIKE ? OR site LIKE ? "
                "ORDER BY updated_at DESC, id DESC", (like,) * 5).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM drafts ORDER BY updated_at DESC, id DESC").fetchall()
        return [dict(r) for r in rows]

    def delete_draft(self, draft_id: int) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
        return cur.rowcount > 0

    def set_input_state(self, draft_id: int, state: str) -> None:
        if state not in INPUT_STATES:
            raise StorageError(f"未知的輸入狀態 {state}")
        with self.conn:
            self.conn.execute("UPDATE drafts SET input_state=?, updated_at=? WHERE id=?", (state, now(), draft_id))
        self.event("input_state", draft_id, state)

    def recover_interrupted_inputs(self) -> int:
        """A 'started' marker left over from a crash means the editor content is uncertain -> 'aborted'."""
        with self.conn:
            cur = self.conn.execute("UPDATE drafts SET input_state='aborted' WHERE input_state='started'")
        if cur.rowcount:
            self.event("recovery", None, f"{cur.rowcount} interrupted typing session(s) marked aborted")
        return cur.rowcount

    # ---------------------------------------------------------------- settings / signature
    def get_setting(self, key: str, default: str = "") -> str:
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                              (key, value))

    def signatures(self) -> list[dict]:
        """Saved signatures [{name, text}], at most MAX_SIGNATURES. A pre-0.3 single signature becomes entry 1."""
        raw = self.get_setting("signature.list", "")
        if raw:
            try:
                items = json.loads(raw)
                return [{"name": str(i.get("name", "")), "text": str(i.get("text", ""))} for i in items][:MAX_SIGNATURES]
            except (ValueError, AttributeError):
                return []
        old = self.get_setting("signature.text", "")
        return [{"name": "簽名檔1", "text": old}] if old.strip() else []

    def _store_signatures(self, items: list[dict]) -> None:
        self.set_setting("signature.list", json.dumps(items, ensure_ascii=False))

    @property
    def active_signature_index(self) -> int:
        n = len(self.signatures())
        try:
            i = int(self.get_setting("signature.active", "0"))
        except ValueError:
            i = 0
        return i if 0 <= i < n else (0 if n else -1)

    def set_active_signature(self, index: int) -> None:
        self.set_setting("signature.active", str(index))

    def save_signature_entry(self, index: int, name: str, text: str) -> int:
        """Update entry `index`, or append when index < 0. Returns the entry index; ValueError when the 10 slots are full."""
        items = self.signatures()
        entry = {"name": name.strip() or f"簽名檔{(index if index >= 0 else len(items)) + 1}", "text": text}
        if 0 <= index < len(items):
            items[index] = entry
        else:
            if len(items) >= MAX_SIGNATURES:
                raise ValueError(f"簽名檔最多 {MAX_SIGNATURES} 則")
            items.append(entry)
            index = len(items) - 1
        self._store_signatures(items)
        self.set_active_signature(index)
        return index

    def delete_signature_entry(self, index: int) -> None:
        items = self.signatures()
        if 0 <= index < len(items):
            del items[index]
            self._store_signatures(items)
            self.set_active_signature(0)

    def favorite_boards(self) -> list[str]:
        try:
            return [str(b) for b in json.loads(self.get_setting("boards.favorites", "[]"))]
        except ValueError:
            return []

    def set_board_favorite(self, board: str, on: bool) -> None:
        favs = [b for b in self.favorite_boards() if b.lower() != board.lower()]
        if on:
            favs.append(board)
        self.set_setting("boards.favorites", json.dumps(favs, ensure_ascii=False))

    @property
    def signature(self) -> str:
        """Text of the active signature ('' when none saved)."""
        items, i = self.signatures(), self.active_signature_index
        return items[i]["text"] if i >= 0 else ""

    def set_signature(self, text: str) -> None:
        i = self.active_signature_index
        self.save_signature_entry(i, self.signatures()[i]["name"] if i >= 0 else "", text)

    # ---------------------------------------------------------------- events (debug trail; never secrets)
    def event(self, kind: str, draft_id: int | None, detail: str = "") -> None:
        try:
            with self.conn:
                self.conn.execute("INSERT INTO events(ts,kind,draft_id,detail) VALUES(?,?,?,?)", (now(), kind, draft_id, detail[:500]))
        except sqlite3.Error:  # pragma: no cover - the trail must never break the app
            log.warning("could not write event %s", kind)

    def events(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]
