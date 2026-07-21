from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from new_core.models import Classification, Event
from new_core.ports import Classifier


DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "category_rules.json"


class RulesClassifier(Classifier):
    """
    Classify events using deterministic app and URL rules.

    Tokens are normalized once while the rules file is loaded, keeping the hot
    classification path to dictionary lookups and a short path-prefix scan.

    Rule priority:
    1. Idle app/title
    2. Exact app token match
    3. Exact hostname match, with the most specific matching path prefix
    4. Unknown
    """

    engine_version = "rules-v1"

    def __init__(self, rules_path: str | Path = DEFAULT_RULES_PATH) -> None:
        """Load category rules and build the indexes used for classification."""
        self._rules_path = Path(rules_path)
        self._rules = self._load_rules(self._rules_path)
        self._app_index, self._domain_index = self._build_indexes(self._rules)

    def classify(self, e: Event) -> Classification:
        """
        Classify an event and return the public classification result.

        The result contains the matched category, a deterministic confidence of
        1.0, the matching rule identifier (if any), and the category's
        ``productive`` flag in its metadata.
        """
        category_id, productive, rule_id = self._classify(e.app, e.title, e.url)
        return Classification(
            category_id=category_id,
            confidence=1.0,
            rule_id=rule_id,
            meta={"productive": productive},
        )

    @staticmethod
    def _load_rules(rules_path: Path) -> dict[str, dict[str, object]]:
        """Read and return the category-rule mapping from a JSON file."""
        return json.loads(rules_path.read_text(encoding="utf-8"))

    @staticmethod
    def _build_indexes(
        rules: dict[str, dict[str, object]],
    ) -> tuple[
        dict[str, tuple[str, bool]],
        dict[str, list[tuple[str, str, bool]]],
    ]:
        """
        Convert raw rules into application and domain lookup indexes.

        Returns a pair containing:
        - an app-name mapping to ``(category_id, productive)``;
        - a hostname mapping to path-specific
          ``(path_prefix, category_id, productive)`` entries.

        Domain entries are ordered from longest to shortest path prefix so the
        most specific matching rule wins.
        """
        app_index: dict[str, tuple[str, bool]] = {}
        domain_index: dict[str, list[tuple[str, str, bool]]] = {}

        for category_id, data in rules.items():
            productive = bool(data.get("productive", False))

            for app_token in data.get("apps", []):
                normalized = str(app_token).strip().lower()
                if normalized:
                    app_index[normalized] = (category_id, productive)

            for domain_token in data.get("domains", []):
                token = str(domain_token).strip().lower()
                if not token:
                    continue

                host, separator, path = token.partition("/")
                host = host.strip()
                if not host:
                    continue

                path_prefix = path.strip()
                if separator and path_prefix and not path_prefix.startswith("/"):
                    path_prefix = "/" + path_prefix

                domain_index.setdefault(host, []).append((path_prefix, category_id, productive))

        for host, entries in domain_index.items():
            domain_index[host] = sorted(entries, key=lambda item: len(item[0]), reverse=True)

        return app_index, domain_index

    def _classify(self, app: str, title: str, url: str) -> tuple[str, bool, str | None]:
        """
        Apply rule priority to normalized event fields.

        Returns ``(category_id, productive, rule_id)``. ``rule_id`` identifies
        the idle, app, or domain rule that matched and is ``None`` when the
        event falls back to the Unknown category.
        """
        normalized_app = (app or "").strip().lower()
        normalized_title = (title or "").strip().lower()

        if normalized_app == "idle" or normalized_title == "idle":
            return "Idle", False, "idle"

        app_match = self._app_index.get(normalized_app)
        if app_match:
            category_id, productive = app_match
            return category_id, productive, f"app:{normalized_app}"

        parsed = urlparse(url or "")
        host = (parsed.hostname or "").strip().lower()
        path = (parsed.path or "").strip().lower()

        for path_prefix, category_id, productive in self._domain_index.get(host, []):
            if not path_prefix or path.startswith(path_prefix):
                token = f"{host}{path_prefix}"
                return category_id, productive, f"domain:{token}"

        return "Unknown", False, None
