from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from new_core.models import Classification, Event


class SQLiteStorage:
    """
    SQLite-backed implementation of the new_core Storage protocol.

    This adapter owns only persistence concerns. It does not decide whether an
    event is valid or what classification should be written.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def insert_event(self, e: Event) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO events (
                    start_ts,
                    end_ts,
                    app,
                    title,
                    url,
                    content_hash
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (e.start_ts, e.end_ts, e.app, e.title, e.url, e.content_hash),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def upsert_engine_classification(
        self,
        event_id: int,
        engine_version: str,
        c: Classification,
    ) -> None:
        meta_json = self._encode_meta(c.meta)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO engine_classifications (
                    event_id,
                    engine_version,
                    category_id,
                    confidence,
                    rule_id,
                    meta_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, engine_version) DO UPDATE SET
                    category_id = excluded.category_id,
                    confidence = excluded.confidence,
                    rule_id = excluded.rule_id,
                    meta_json = excluded.meta_json,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    event_id,
                    engine_version,
                    c.category_id,
                    c.confidence,
                    c.rule_id,
                    meta_json,
                ),
            )
            self._conn.commit()

    def set_user_override(
        self,
        event_id: int,
        category_id: str,
        note: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO user_overrides (
                    event_id,
                    category_id,
                    note
                ) VALUES (?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    category_id = excluded.category_id,
                    note = excluded.note,
                    created_at = CURRENT_TIMESTAMP
                """,
                (event_id, category_id, note),
            )
            self._conn.commit()

    def clear_user_override(self, event_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM user_overrides WHERE event_id = ?",
                (event_id,),
            )
            self._conn.commit()

    def _configure_connection(self) -> None:
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA journal_mode = WAL;")

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_ts REAL NOT NULL,
                    end_ts REAL NOT NULL,
                    app TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    content_hash TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS engine_classifications (
                    event_id INTEGER NOT NULL,
                    engine_version TEXT NOT NULL,
                    category_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    rule_id TEXT,
                    meta_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (event_id, engine_version),
                    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_overrides (
                    event_id INTEGER PRIMARY KEY,
                    category_id TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_events_start_ts
                ON events(start_ts);
                """
            )
            self._conn.commit()

    @staticmethod
    def _encode_meta(meta: Optional[dict[str, object]]) -> Optional[str]:
        if meta is None:
            return None
        return json.dumps(meta, sort_keys=True, separators=(",", ":"))
