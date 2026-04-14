from __future__ import annotations
from typing import Protocol, Callable, Optional
from .models import Event, Classification


class EventSource(Protocol):
    """
    Produces finalized time segments as Events (start_ts/end_ts + metadata).
    """
    def start(self, emit: Callable[[Event], None]) -> None: ...
    def stop(self) -> None: ...

class AppOverride(Protocol):
    """
    Supplies better (title, url) metadata for a specific app when available.
    Return None if unavailable or stale.
    """
    def get(self) -> tuple[str, str] | None: ...

class Classifier(Protocol):
    """
    Pure-ish classifier. Returns a derived classification for an event.
    """
    @property
    def engine_version(self) -> str: ...
    def classify(self, e: Event) -> Classification: ...


class Storage(Protocol):
    """
    Storage persists finalized events plus derived/user-authored labels.
    Keep this interface stable; it is the backbone of the app.
    """

    # Raw events
    def insert_event(self, e: Event) -> int:
        """Insert one finalized raw event segment. Return event_id."""
        ...

    # Engine classifications (derived, versioned)
    def upsert_engine_classification(
        self,
        event_id: int,
        engine_version: str,
        c: Classification,
    ) -> None:
        ...

    # User overrides (authoritative)
    def set_user_override(self, event_id: int, category_id: str, note: Optional[str] = None) -> None:
        ...

    def clear_user_override(self, event_id: int) -> None:
        ...


class Publisher(Protocol):
    """
    Used by AppService to notify UI/dashboard about changes.
    Current implementation is no-op, future implementations can be in-process callbacks or websocket broadcast.
    """
    def event_recorded(self, event_id: int) -> None: ...
    def label_updated(self, event_id: int) -> None: ...
    def override_updated(self, event_id: int) -> None: ...
