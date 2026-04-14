from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .models import Event
from .ports import EventSource, Storage, Classifier, Publisher


class NoopPublisher:
    def event_recorded(self, event_id: int) -> None: pass
    def label_updated(self, event_id: int) -> None: pass
    def override_updated(self, event_id: int) -> None: pass


@dataclass
class AppServiceConfig:
    """
    Tweak behavior without changing logic.
    """
    classify_on_ingest: bool = True  # classify immediately as events arrive


class AppService:
    """
    Orchestrates finalized-event ingestion:
      EventSource -> Storage (raw segments) -> Classifier -> Storage (derived labels)
    Also provides methods for user overrides that the dashboard can call.
    """

    def __init__(
        self,
        source: EventSource,
        storage: Storage,
        classifier: Optional[Classifier] = None,
        publisher: Optional[Publisher] = None,
        config: Optional[AppServiceConfig] = None,
    ) -> None:
        self._source = source
        self._storage = storage
        self._classifier = classifier
        self._publisher = publisher or NoopPublisher()
        self._config = config or AppServiceConfig()

        self._running = False

    # -------- lifecycle --------
    def start(self) -> None:
        """
        Start listening. Typically run this from a backend process.
        """
        self._running = True
        self._source.start(self._on_event)

    def stop(self) -> None:
        self._running = False
        self._source.stop()

    # -------- ingestion callback --------
    def _on_event(self, e: Event) -> None:
        """
        Called by the source when it finalizes a stable foreground segment.
        This must be fast and robust (don't crash on classifier errors).
        """
        if not self._running:
            return

        if e.end_ts is None or e.end_ts < e.start_ts:
            return

        # 1) Persist the finalized segment as-is.
        new_id = self._storage.insert_event(e)
        self._publisher.event_recorded(new_id)

        # 2) Classify immediately (optional)
        if self._config.classify_on_ingest and self._classifier is not None:
            try:
                c = self._classifier.classify(e)
                self._storage.upsert_engine_classification(
                    event_id=new_id,
                    engine_version=self._classifier.engine_version,
                    c=c,
                )
                self._publisher.label_updated(new_id)
            except Exception:
                # In production: log + metric, but never stop ingestion.
                return

    # -------- dashboard override API --------
    def set_override(self, event_id: int, category_id: str, note: Optional[str] = None) -> None:
        """
        Called by dashboard when user changes a label.
        """
        self._storage.set_user_override(event_id, category_id, note=note)
        self._publisher.override_updated(event_id)

    def clear_override(self, event_id: int) -> None:
        self._storage.clear_user_override(event_id)
        self._publisher.override_updated(event_id)
