import json
from pathlib import Path

import pytest

from logger import categorize
from logger.categorize import categorize as categorize_fn


def test_categorize_matches_productive_rule():
    category, productive = categorize_fn("Visual Studio Code", "main.py", "")
    assert category == "Coding"
    assert productive is True


def test_categorize_conditional_productive():
    category, productive = categorize_fn(
        "Google Chrome",
        "ChatGPT - prompt engineering",
        "https://chatgpt.com/session",
    )
    assert category == "Research"
    assert productive is True


def test_categorize_conditional_not_productive():
    category, productive = categorize_fn(
        "Google Chrome",
        "Reddit - r/python",
        "https://www.reddit.com/r/python",
    )
    assert category == "Social/Forums"
    assert productive is False

def test_categorize_hupu():
    category, productive = categorize_fn(
        "firefox",
        "虎扑体育-虎扑网",
        "https://www.hupu.com"
    )
    assert category == "Social/Forums"
    assert productive is False

def test_categorize_zhihu():
    category, productive = categorize_fn(
        "firefox",
        "(75 封私信 / 80 条消息) 首页 - 知乎",
        "https://www.zhihu.com/"
    )
    assert category == "Social/Forums"
    assert productive is False

def test_categorize_no_rule_match():
    category, productive = categorize_fn("Some Unknown App", "Untitled", "")
    assert category == "Unknown"
    assert productive is False


def _configure_keyword_index(tmp_path, monkeypatch, data):
    keyword_path = Path(tmp_path) / "keyword_index.json"
    keyword_path.write_text(json.dumps(data))
    monkeypatch.setattr(categorize, "KEYWORD_INDEX_PATH", keyword_path)
    monkeypatch.setattr(categorize, "KEYWORD_INDEX", json.loads(json.dumps(data)), raising=False)
    monkeypatch.setattr(categorize, "KEYWORD_LOOKUP", categorize._build_keyword_lookup(data), raising=False)
    categorize.KEYWORD_SESSION_STATE.clear()


def test_keyword_index_used_for_unknown(tmp_path, monkeypatch):
    data = {"Entertainment": [{"keyword": "youtube video", "count": 1}]}
    _configure_keyword_index(tmp_path, monkeypatch, data)

    category, productive = categorize_fn("Unknown App", "Watching youtube video", "", context_key="ctx-1")
    assert category == "Entertainment"
    assert productive is False


def test_keyword_session_counts_once_per_context(tmp_path, monkeypatch):
    data = {"Research": [{"keyword": "prompt engineering", "count": 1}]}
    _configure_keyword_index(tmp_path, monkeypatch, data)

    context = "chatgpt|prompt"
    first = categorize_fn("Google Chrome", "Prompt engineering guide", "https://chatgpt.com/session", context_key=context)
    second = categorize_fn("Google Chrome", "Prompt engineering guide", "https://chatgpt.com/session", context_key=context)

    assert first[0] == "Research"
    assert second[0] == "Research"

    stored = json.loads(Path(categorize.KEYWORD_INDEX_PATH).read_text())
    assert stored["Research"][0]["count"] == 2
