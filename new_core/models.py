from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Any


@dataclass(frozen=True)
class Event:
    """
    A segment of time during which the frontmost context is stable.
    end_ts can be None while "open" (not yet closed).
    """
    start_ts: float
    end_ts: Optional[float]
    app: str
    title: str
    url: str = ""
    content_hash: Optional[str] = None  # optional: hash(app|title|url) for caching/rules


@dataclass(frozen=True)
class Classification:
    """
    Derived label from engine (versioned) or user override.
    """
    category_id: str
    confidence: float = 1.0
    rule_id: Optional[str] = None
    meta: Optional[dict[str, Any]] = None  # store anything else (matched pattern, etc.)
