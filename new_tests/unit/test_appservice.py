from __future__ import annotations

import pytest

from dataclasses import dataclass, field
from typing import Callable, Optional

from new_core.appservice import AppService
from new_core.models import Classification, Event


class FakeSource:
    def __init__(self) -> None:
        self.emit: Optional[Callable[[Event], None]] = None
        self.stopped = False

    def start(self, emit: Callable[[Event], None]) -> None:
        self.emit = emit

    def stop(self) -> None:
        self.stopped = True


@dataclass
class FakeStorage:
    inserted_events: list[Event] = field(default_factory=list)
    engine_labels: list[tuple[int, str, Classification]] = field(default_factory=list)
    overrides_set: list[tuple[int, str, Optional[str]]] = field(default_factory=list)
    overrides_cleared: list[int] = field(default_factory=list)

    def insert_event(self, e: Event) -> int:
        self.inserted_events.append(e)
        return len(self.inserted_events)

    def upsert_engine_classification(
        self,
        event_id: int,
        engine_version: str,
        c: Classification,
    ) -> None:
        self.engine_labels.append((event_id, engine_version, c))

    def set_user_override(
        self,
        event_id: int,
        category_id: str,
        note: Optional[str] = None,
    ) -> None:
        self.overrides_set.append((event_id, category_id, note))

    def clear_user_override(self, event_id: int) -> None:
        self.overrides_cleared.append(event_id)


class FakeClassifier:
    engine_version = "rules-v1"

    def classify(self, e: Event) -> Classification:
        return Classification(category_id="work", confidence=0.9)


@dataclass
class FakePublisher:
    recorded_ids: list[int] = field(default_factory=list)
    labeled_ids: list[int] = field(default_factory=list)
    override_ids: list[int] = field(default_factory=list)

    def event_recorded(self, event_id: int) -> None:
        self.recorded_ids.append(event_id)

    def label_updated(self, event_id: int) -> None:
        self.labeled_ids.append(event_id)

    def override_updated(self, event_id: int) -> None:
        self.override_ids.append(event_id)

@pytest.mark.unit
def test_appservice_persists_and_classifies_finalized_events() -> None:
    source = FakeSource()
    storage = FakeStorage()
    publisher = FakePublisher()
    classifier = FakeClassifier()
    app = AppService(
        source=source,
        storage=storage,
        classifier=classifier,
        publisher=publisher,
    )

    app.start()
    assert source.emit is not None

    event = Event(
        start_ts=10.0,
        end_ts=12.5,
        app="Safari",
        title="Docs",
        url="https://example.com",
    )
    source.emit(event)

    assert storage.inserted_events == [event]
    assert publisher.recorded_ids == [1]
    assert storage.engine_labels == [
        (1, "rules-v1", Classification(category_id="work", confidence=0.9))
    ]
    assert publisher.labeled_ids == [1]

@pytest.mark.unit
def test_appservice_ignores_open_or_invalid_events() -> None:
    source = FakeSource()
    storage = FakeStorage()
    publisher = FakePublisher()
    app = AppService(source=source, storage=storage, publisher=publisher)

    app.start()
    assert source.emit is not None

    source.emit(Event(start_ts=10.0, end_ts=None, app="Finder", title="", url=""))
    source.emit(Event(start_ts=10.0, end_ts=9.0, app="Finder", title="", url=""))

    assert storage.inserted_events == []
    assert publisher.recorded_ids == []

@pytest.mark.unit
def test_appservice_override_api_updates_storage_and_publisher() -> None:
    source = FakeSource()
    storage = FakeStorage()
    publisher = FakePublisher()
    app = AppService(source=source, storage=storage, publisher=publisher)

    app.set_override(7, "focus", note="manual correction")
    app.clear_override(7)

    assert storage.overrides_set == [(7, "focus", "manual correction")]
    assert storage.overrides_cleared == [7]
    assert publisher.override_ids == [7, 7]
