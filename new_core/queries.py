from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol


LabelSource = Literal["user", "engine", "unknown"]
Granularity = Literal["auto", "hour", "day", "week", "month"]
ResolvedGranularity = Literal["hour", "day", "week", "month"]
GroupBy = Literal["category", "app"]


def choose_granularity(start_ts: float, end_ts: float) -> ResolvedGranularity:
    """Choose a readable chart scale for a query interval."""
    if end_ts <= start_ts:
        raise ValueError("end_ts must be greater than start_ts")

    duration = end_ts - start_ts
    if duration <= 2 * 24 * 60 * 60:
        return "hour"
    if duration <= 8 * 7 * 24 * 60 * 60:
        return "day"
    if duration <= 18 * 30.4375 * 24 * 60 * 60:
        return "week"
    return "month"


@dataclass(frozen=True)
class RecordedEvent:
    """A persisted event together with its effective classification."""

    event_id: int
    start_ts: float
    end_ts: float
    app: str
    title: str
    url: str
    content_hash: Optional[str]
    category_id: str
    label_source: LabelSource
    confidence: Optional[float] = None
    rule_id: Optional[str] = None
    engine_version: Optional[str] = None
    classification_meta: Optional[dict[str, object]] = None
    override_note: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        return self.end_ts - self.start_ts


class EventQueries(Protocol):
    """Read-side contract used by dashboards, reports, and exports."""

    def events_in_range(
        self,
        start_ts: float,
        end_ts: float,
    ) -> list[RecordedEvent]: ...

    def category_totals(self, start_ts: float, end_ts: float) -> dict[str, float]: ...

    def app_totals(self, start_ts: float, end_ts: float) -> dict[str, float]: ...

    def daily_totals(
        self,
        start_ts: float,
        end_ts: float,
    ) -> dict[str, dict[str, float]]: ...

    def bucketed_totals(
        self,
        start_ts: float,
        end_ts: float,
        *,
        granularity: Granularity = "auto",
        group_by: GroupBy = "category",
    ) -> dict[str, dict[str, float]]: ...
