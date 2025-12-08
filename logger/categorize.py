import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "category_rules.json"
with open(CONFIG_PATH) as f:
    CATEGORY_RULES = json.load(f)

def categorize(app, title, url):
    """
    Rule based classifier. Rules are defined by category_rules.json in config.
    """
    normalized_app = (app or "").lower()
    normalized_title = (title or "").lower()

    if normalized_app == "idle" or normalized_title == "idle":
        return "Idle", False

    for category, data in CATEGORY_RULES.items():
        rules = data["rules"]
        for rule in rules:
            lower_rule = rule.lower()
            if lower_rule in normalized_app or lower_rule in normalized_title:
                productive_flag = data.get("productive", False)
                if productive_flag == "conditional":
                    for address in data.get("productive_urls", []):
                        if address.lower() in (url or "").lower():
                            return category, True
                    for keyword in data.get("productive_keywords", []):
                        if keyword.lower() in normalized_title:
                            return category, True
                    return category, False
                return category, productive_flag
    return "Unknown", False

# TODO: can use a classification model for unknown front apps
