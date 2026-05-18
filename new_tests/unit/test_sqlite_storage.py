from __future__ import annotations

import json
import sqlite3

import pytest

from new_core.models import Classification, Event
from new_storage.sqlite import SQLiteStorage


@pytest.mark.unit
def test_sqlite_storage_inserts_events(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "activity.sqlite3")
    event = Event(
        start_ts=10.0,
        end_ts=12.5,
        app="Safari",
        title="Docs",
        url="https://example.com",
        content_hash="abc123",
    )

    event_id = storage.insert_event(event)

    assert event_id == 1

    with sqlite3.connect(storage.db_path) as conn:
        row = conn.execute(
            """
            SELECT start_ts, end_ts, app, title, url, content_hash
            FROM events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()

    assert row == (
        10.0,
        12.5,
        "Safari",
        "Docs",
        "https://example.com",
        "abc123",
    )

    storage.close()


@pytest.mark.unit
def test_sqlite_storage_upserts_engine_classifications(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "activity.sqlite3")
    event_id = storage.insert_event(
        Event(start_ts=1.0, end_ts=2.0, app="Code", title="Editor", url="")
    )

    storage.upsert_engine_classification(
        event_id,
        "rules-v1",
        Classification(
            category_id="work",
            confidence=0.7,
            rule_id="rule-1",
            meta={"source": "rules"},
        ),
    )
    storage.upsert_engine_classification(
        event_id,
        "rules-v1",
        Classification(
            category_id="focus",
            confidence=0.95,
            rule_id="rule-2",
            meta={"source": "override-pass"},
        ),
    )

    with sqlite3.connect(storage.db_path) as conn:
        rows = conn.execute(
            """
            SELECT engine_version, category_id, confidence, rule_id, meta_json
            FROM engine_classifications
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchall()

    assert rows == [
        ("rules-v1", "focus", 0.95, "rule-2", json.dumps({"source": "override-pass"}, sort_keys=True, separators=(",", ":")))
    ]

    storage.close()


@pytest.mark.unit
def test_sqlite_storage_sets_and_clears_user_overrides(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "activity.sqlite3")
    event_id = storage.insert_event(
        Event(start_ts=1.0, end_ts=2.0, app="Code", title="Editor", url="")
    )

    storage.set_user_override(event_id, "focus", note="manual")
    storage.set_user_override(event_id, "deep-work", note="adjusted")

    with sqlite3.connect(storage.db_path) as conn:
        row = conn.execute(
            """
            SELECT category_id, note
            FROM user_overrides
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()

    assert row == ("deep-work", "adjusted")

    storage.clear_user_override(event_id)

    with sqlite3.connect(storage.db_path) as conn:
        row = conn.execute(
            "SELECT category_id, note FROM user_overrides WHERE event_id = ?",
            (event_id,),
        ).fetchone()

    assert row is None

    storage.close()
