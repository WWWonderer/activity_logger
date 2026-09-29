from __future__ import annotations

from datetime import datetime, timezone

import pytest

from new_core.models import CapturedEvent, Classification
from new_core.queries import (
    choose_granularity,
)
from new_storage.sqlite import SQLiteStorage
from new_storage.sqlite_queries import SQLiteEventQueries


@pytest.fixture
def database(tmp_path):
    storage = SQLiteStorage(tmp_path / "activity.sqlite3")
    queries = SQLiteEventQueries(storage.db_path)
    yield storage, queries
    queries.close()
    storage.close()


@pytest.mark.unit
def test_events_in_range_resolves_effective_label_precedence(database) -> None:
    storage, queries = database
    event_id = storage.insert_event(
        CapturedEvent(start_ts=10.0, end_ts=20.0, app="Code", title="Editor", url="")
    )
    unknown_id = storage.insert_event(
        CapturedEvent(start_ts=30.0, end_ts=40.0, app="Finder", title="Files", url="")
    )

    storage.upsert_engine_classification(
        event_id,
        "rules-v1",
        Classification(
            category_id="Coding",
            confidence=0.8,
            rule_id="app:code",
            meta={"productive": True},
        ),
    )
    storage.upsert_engine_classification(
        event_id,
        "rules-v2",
        Classification(category_id="Deep Work", confidence=0.9, rule_id="app:code-v2"),
    )

    records = queries.events_in_range(0.0, 50.0)
    assert [record.event_id for record in records] == [event_id, unknown_id]
    assert records[1].category_id == "Unknown"
    assert records[1].label_source == "unknown"

    classified = records[0]
    assert classified.category_id == "Deep Work"
    assert classified.label_source == "engine"
    assert classified.engine_version == "rules-v2"
    assert classified.confidence == 0.9

    storage.set_user_override(event_id, "Meetings", note="manual correction")
    overridden = queries.events_in_range(15.0, 16.0)[0]
    assert overridden.category_id == "Meetings"
    assert overridden.label_source == "user"
    assert overridden.override_note == "manual correction"
    assert overridden.engine_version is None
    assert overridden.confidence is None

    storage.clear_user_override(event_id)
    assert queries.events_in_range(15.0, 16.0)[0].category_id == "Deep Work"


@pytest.mark.unit
def test_events_in_range_returns_all_overlaps_in_timeline_order(database) -> None:
    storage, queries = database
    first_id = storage.insert_event(
        CapturedEvent(start_ts=0.0, end_ts=10.0, app="A", title="First", url="")
    )
    second_id = storage.insert_event(
        CapturedEvent(start_ts=10.0, end_ts=20.0, app="B", title="Second", url="")
    )
    third_id = storage.insert_event(
        CapturedEvent(start_ts=20.0, end_ts=30.0, app="C", title="Third", url="")
    )

    assert [record.event_id for record in queries.events_in_range(5.0, 25.0)] == [
        first_id,
        second_id,
        third_id,
    ]
    assert queries.events_in_range(30.0, 40.0) == []


@pytest.mark.unit
def test_category_and_app_totals_clip_events_to_requested_range(database) -> None:
    storage, queries = database
    code_id = storage.insert_event(
        CapturedEvent(start_ts=0.0, end_ts=20.0, app="Code", title="Editor", url="")
    )
    browser_id = storage.insert_event(
        CapturedEvent(start_ts=15.0, end_ts=35.0, app="Firefox", title="Docs", url="")
    )
    storage.insert_event(
        CapturedEvent(start_ts=18.0, end_ts=22.0, app="Finder", title="Files", url="")
    )
    storage.upsert_engine_classification(
        code_id,
        "rules-v1",
        Classification(category_id="Coding"),
    )
    storage.upsert_engine_classification(
        browser_id,
        "rules-v1",
        Classification(category_id="Research"),
    )
    storage.set_user_override(browser_id, "Coding")

    assert queries.category_totals(10.0, 25.0) == {
        "Coding": 20.0,
        "Unknown": 4.0,
    }
    assert queries.app_totals(10.0, 25.0) == {
        "Code": 10.0,
        "Firefox": 10.0,
        "Finder": 4.0,
    }


@pytest.mark.unit
def test_daily_totals_split_events_at_local_midnight(database) -> None:
    storage, queries = database
    start = datetime(2026, 8, 11, 23, 59, 30, tzinfo=timezone.utc).timestamp()
    end = datetime(2026, 8, 12, 0, 0, 30, tzinfo=timezone.utc).timestamp()
    event_id = storage.insert_event(
        CapturedEvent(start_ts=start, end_ts=end, app="Code", title="Late work", url="")
    )
    storage.upsert_engine_classification(
        event_id,
        "rules-v1",
        Classification(category_id="Coding"),
    )

    assert queries.daily_totals(start, end) == {
        "2026-08-11": {"Coding": 30.0},
        "2026-08-12": {"Coding": 30.0},
    }


@pytest.mark.unit
def test_queries_reject_invalid_ranges(database) -> None:
    _, queries = database

    with pytest.raises(ValueError, match="end_ts"):
        queries.category_totals(10.0, 10.0)
    with pytest.raises(ValueError, match="end_ts"):
        queries.events_in_range(10.0, 10.0)


@pytest.mark.unit
def test_choose_granularity_adjusts_to_query_duration() -> None:
    day = 24 * 60 * 60

    assert choose_granularity(0.0, 2 * day) == "hour"
    assert choose_granularity(0.0, 2 * day + 1) == "day"
    assert choose_granularity(0.0, 8 * 7 * day + 1) == "week"
    assert choose_granularity(0.0, 19 * 31 * day) == "month"


@pytest.mark.unit
def test_bucketed_totals_auto_uses_hourly_buckets_and_supports_app_grouping(database) -> None:
    storage, queries = database
    start = datetime(2026, 8, 12, 0, 30, tzinfo=timezone.utc).timestamp()
    end = datetime(2026, 8, 12, 2, 0, tzinfo=timezone.utc).timestamp()
    storage.insert_event(
        CapturedEvent(start_ts=start, end_ts=end, app="Code", title="Editor", url="")
    )

    assert queries.bucketed_totals(start, end, group_by="app") == {
        "2026-08-12T00:00:00+00:00": {"Code": 1800.0},
        "2026-08-12T01:00:00+00:00": {"Code": 3600.0},
    }


@pytest.mark.unit
def test_bucketed_totals_uses_calendar_week_and_month_boundaries(database) -> None:
    storage, queries = database
    start = datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc).timestamp()
    end = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc).timestamp()
    event_id = storage.insert_event(
        CapturedEvent(start_ts=start, end_ts=end, app="Code", title="Editor", url="")
    )
    storage.upsert_engine_classification(
        event_id,
        "rules-v1",
        Classification(category_id="Coding"),
    )

    assert queries.bucketed_totals(start, end, granularity="week") == {
        "2026-08-24T00:00:00+00:00": {"Coding": 1800.0},
        "2026-08-31T00:00:00+00:00": {"Coding": 88200.0},
    }
    assert queries.bucketed_totals(start, end, granularity="month") == {
        "2026-08-01T00:00:00+00:00": {"Coding": 88200.0},
        "2026-09-01T00:00:00+00:00": {"Coding": 1800.0},
    }


@pytest.mark.unit
def test_hourly_buckets_distinguish_repeated_dst_hour(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "activity.sqlite3")
    queries = SQLiteEventQueries(storage.db_path, timezone_name="America/Montreal")
    start = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).timestamp()
    end = datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc).timestamp()
    storage.insert_event(
        CapturedEvent(start_ts=start, end_ts=end, app="Code", title="DST", url="")
    )

    try:
        assert queries.bucketed_totals(start, end, granularity="hour", group_by="app") == {
            "2026-11-01T01:00:00-04:00": {"Code": 1800.0},
            "2026-11-01T01:00:00-05:00": {"Code": 3600.0},
            "2026-11-01T02:00:00-05:00": {"Code": 1800.0},
        }
    finally:
        queries.close()
        storage.close()


@pytest.mark.unit
def test_bucketed_totals_rejects_invalid_options(database) -> None:
    _, queries = database

    with pytest.raises(ValueError, match="granularity"):
        queries.bucketed_totals(0.0, 1.0, granularity="quarter")
    with pytest.raises(ValueError, match="group_by"):
        queries.bucketed_totals(0.0, 1.0, group_by="title")
