from __future__ import annotations

import pytest

from new_classifiers.rules import RulesClassifier
from new_core.models import Classification, Event


@pytest.mark.unit
def test_rules_classifier_handles_idle_events() -> None:
    classifier = RulesClassifier()

    result = classifier.classify(
        Event(
            start_ts=1.0,
            end_ts=2.0,
            app="Idle",
            title="Idle",
            url="",
        )
    )

    assert result == Classification(
        category_id="Idle",
        confidence=1.0,
        rule_id="idle",
        meta={"productive": False},
    )
    assert classifier.engine_version == "rules-v1"


@pytest.mark.unit
def test_rules_classifier_matches_app_rules() -> None:
    classifier = RulesClassifier()

    result = classifier.classify(
        Event(
            start_ts=1.0,
            end_ts=2.0,
            app="Visual Studio Code",
            title="main.py",
            url="",
        )
    )

    assert result.category_id == "Coding"
    assert result.rule_id == "app:visual studio code"
    assert result.meta == {"productive": True}


@pytest.mark.unit
def test_rules_classifier_matches_domain_path_rules() -> None:
    classifier = RulesClassifier()

    result = classifier.classify(
        Event(
            start_ts=1.0,
            end_ts=2.0,
            app="Firefox",
            title="Search results",
            url="https://www.google.com/search?q=activity+logger",
        )
    )

    assert result.category_id == "Research"
    assert result.rule_id == "domain:www.google.com/search"
    assert result.meta == {"productive": True}
