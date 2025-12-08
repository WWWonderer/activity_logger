from logger.categorize import categorize


def test_categorize_matches_productive_rule():
    category, productive = categorize("Visual Studio Code", "main.py", "")
    assert category == "Coding"
    assert productive is True


def test_categorize_conditional_productive():
    category, productive = categorize(
        "Google Chrome",
        "ChatGPT - prompt engineering",
        "https://chatgpt.com/session",
    )
    assert category == "Browsing"
    assert productive is True


def test_categorize_conditional_not_productive():
    category, productive = categorize(
        "Google Chrome",
        "Reddit - r/python",
        "https://www.reddit.com/r/python",
    )
    assert category == "Browsing"
    assert productive is False


def test_categorize_no_rule_match():
    category, productive = categorize("Some Unknown App", "Untitled", "")
    assert category == "Unknown"
    assert productive is False
