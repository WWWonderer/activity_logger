from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from new_core.queries import (
    Granularity,
    GroupBy,
    RecordedEvent,
    ResolvedGranularity,
    choose_granularity,
)


_EFFECTIVE_EVENTS_CTE = """
WITH ranked_engine AS (
    SELECT
        rowid AS classification_rowid,
        event_id,
        engine_version,
        category_id,
        confidence,
        rule_id,
        meta_json,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY created_at DESC, rowid DESC
        ) AS rank
    FROM engine_classifications
),
effective_events AS (
    SELECT
        e.id AS event_id,
        e.start_ts,
        e.end_ts,
        e.app,
        e.title,
        e.url,
        e.content_hash,
        COALESCE(u.category_id, c.category_id, 'Unknown') AS category_id,
        CASE
            WHEN u.event_id IS NOT NULL THEN 'user'
            WHEN c.event_id IS NOT NULL THEN 'engine'
            ELSE 'unknown'
        END AS label_source,
        CASE WHEN u.event_id IS NULL THEN c.confidence END AS confidence,
        CASE WHEN u.event_id IS NULL THEN c.rule_id END AS rule_id,
        CASE WHEN u.event_id IS NULL THEN c.engine_version END AS engine_version,
        CASE WHEN u.event_id IS NULL THEN c.meta_json END AS meta_json,
        u.note AS override_note
    FROM events AS e
    LEFT JOIN ranked_engine AS c
        ON c.event_id = e.id AND c.rank = 1
    LEFT JOIN user_overrides AS u
        ON u.event_id = e.id
)
"""


def _resolve_granularity(
    granularity: Granularity,
    start_ts: float,
    end_ts: float,
) -> ResolvedGranularity:
    if granularity == "auto":
        return choose_granularity(start_ts, end_ts)
    if granularity not in ("hour", "day", "week", "month"):
        raise ValueError("granularity must be 'auto', 'hour', 'day', 'week', or 'month'")
    return granularity


def _range_clause(
    start_ts: Optional[float],
    end_ts: Optional[float],
) -> tuple[str, list[float]]:
    clauses: list[str] = []
    parameters: list[float] = []
    if start_ts is not None:
        clauses.append("end_ts > ?")
        parameters.append(start_ts)
    if end_ts is not None:
        clauses.append("start_ts < ?")
        parameters.append(end_ts)
    if not clauses:
        return "", parameters
    return "WHERE " + " AND ".join(clauses), parameters


def _validate_range(start_ts: float, end_ts: float) -> None:
    if end_ts <= start_ts:
        raise ValueError("end_ts must be greater than start_ts")


def _clipped_duration(event: RecordedEvent, start_ts: float, end_ts: float) -> float:
    return max(0.0, min(event.end_ts, end_ts) - max(event.start_ts, start_ts))


def _sorted_totals(totals: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))


def _recorded_event(row: sqlite3.Row) -> RecordedEvent:
    meta_json = row["meta_json"]
    return RecordedEvent(
        event_id=int(row["event_id"]),
        start_ts=float(row["start_ts"]),
        end_ts=float(row["end_ts"]),
        app=str(row["app"]),
        title=str(row["title"]),
        url=str(row["url"]),
        content_hash=row["content_hash"],
        category_id=str(row["category_id"]),
        label_source=row["label_source"],
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        rule_id=row["rule_id"],
        engine_version=row["engine_version"],
        classification_meta=json.loads(meta_json) if meta_json is not None else None,
        override_note=row["override_note"],
    )


class SQLiteEventQueries:
    """SQLite implementation of the read-side event query contract."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        timezone_name: str = "UTC",
    ) -> None:
        self._db_path = Path(db_path)
        self._timezone: tzinfo = ZoneInfo(timezone_name) if timezone_name != "UTC" else timezone.utc
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def events_in_range(
        self,
        start_ts: float,
        end_ts: float,
    ) -> list[RecordedEvent]:
        """Return every event overlapping the interval in timeline order."""
        _validate_range(start_ts, end_ts)
        where_sql, parameters = _range_clause(start_ts, end_ts)
        sql = (
            _EFFECTIVE_EVENTS_CTE
            + """
            SELECT *
            FROM effective_events
            """
            + where_sql
            + """
            ORDER BY start_ts ASC, event_id ASC
            """
        )

        with self._lock:
            rows = self._conn.execute(sql, parameters).fetchall()
        return [_recorded_event(row) for row in rows]

    def category_totals(self, start_ts: float, end_ts: float) -> dict[str, float]:
        events = self._events_for_aggregation(start_ts, end_ts)
        totals: defaultdict[str, float] = defaultdict(float)
        for event in events:
            totals[event.category_id] += _clipped_duration(event, start_ts, end_ts)
        return dict(_sorted_totals(totals))

    def app_totals(self, start_ts: float, end_ts: float) -> dict[str, float]:
        events = self._events_for_aggregation(start_ts, end_ts)
        totals: defaultdict[str, float] = defaultdict(float)
        for event in events:
            totals[event.app] += _clipped_duration(event, start_ts, end_ts)
        return dict(_sorted_totals(totals))

    def daily_totals(self, start_ts: float, end_ts: float) -> dict[str, dict[str, float]]:
        buckets = self.bucketed_totals(
            start_ts,
            end_ts,
            granularity="day",
            group_by="category",
        )
        return {
            bucket_start[:10]: category_totals
            for bucket_start, category_totals in buckets.items()
        }

    def bucketed_totals(
        self,
        start_ts: float,
        end_ts: float,
        *,
        granularity: Granularity = "auto",
        group_by: GroupBy = "category",
    ) -> dict[str, dict[str, float]]:
        """Split an arbitrary query interval into display-ready time buckets."""
        _validate_range(start_ts, end_ts)
        resolved = _resolve_granularity(granularity, start_ts, end_ts)
        if group_by not in ("category", "app"):
            raise ValueError("group_by must be 'category' or 'app'")

        events = self._events_for_aggregation(start_ts, end_ts)
        totals: defaultdict[float, defaultdict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

        for event in events:
            cursor = max(event.start_ts, start_ts)
            clipped_end = min(event.end_ts, end_ts)
            group = event.category_id if group_by == "category" else event.app

            while cursor < clipped_end:
                bucket_start = self._bucket_start(cursor, resolved)
                next_boundary = self._next_bucket_start(bucket_start, resolved)
                segment_end = min(clipped_end, next_boundary)
                totals[bucket_start][group] += segment_end - cursor
                cursor = segment_end

        return {
            datetime.fromtimestamp(bucket_start, self._timezone).isoformat(): dict(
                sorted(groups.items())
            )
            for bucket_start, groups in sorted(totals.items())
        }

    def _events_for_aggregation(self, start_ts: float, end_ts: float) -> list[RecordedEvent]:
        _validate_range(start_ts, end_ts)
        where_sql, parameters = _range_clause(start_ts, end_ts)
        sql = _EFFECTIVE_EVENTS_CTE + "SELECT * FROM effective_events " + where_sql
        with self._lock:
            rows = self._conn.execute(sql, parameters).fetchall()
        return [_recorded_event(row) for row in rows]

    def _bucket_start(self, timestamp: float, granularity: ResolvedGranularity) -> float:
        local = datetime.fromtimestamp(timestamp, self._timezone)
        if granularity == "hour":
            return local.replace(minute=0, second=0, microsecond=0).timestamp()
        if granularity == "day":
            bucket_date = local.date()
        elif granularity == "week":
            bucket_date = local.date() - timedelta(days=local.weekday())
        else:
            bucket_date = date(local.year, local.month, 1)
        return datetime.combine(bucket_date, time.min, self._timezone).timestamp()

    def _next_bucket_start(
        self,
        bucket_start: float,
        granularity: ResolvedGranularity,
    ) -> float:
        if granularity == "hour":
            return bucket_start + 60 * 60

        local_start = datetime.fromtimestamp(bucket_start, self._timezone)
        if granularity == "day":
            next_date = local_start.date() + timedelta(days=1)
        elif granularity == "week":
            next_date = local_start.date() + timedelta(days=7)
        else:
            year = local_start.year + (1 if local_start.month == 12 else 0)
            month = 1 if local_start.month == 12 else local_start.month + 1
            next_date = date(year, month, 1)
        return datetime.combine(next_date, time.min, self._timezone).timestamp()
