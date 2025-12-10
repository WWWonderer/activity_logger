import json
import os
from pathlib import Path
from openai import OpenAI
from datetime import datetime

RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "category_rules.json"
AI_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "ai_config.json"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _load_categories():
    try:
        data = json.loads(RULES_PATH.read_text())
    except Exception:
        return {}
    return {
        name: {
            "productive": details.get("productive"),
        }
        for name, details in data.items()
    }


def _load_ai_config():
    if AI_CONFIG_PATH.exists():
        try:
            return json.loads(AI_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def openai_categorize(app, title, url):
    """
    AI callback compatible with categorize_with_ai. Requires OPENAI_API_KEY.

    Returns a dict: {"category": str, "productive": bool, "confidence": float, "rationale": str}
    """
    cfg = _load_ai_config()

    api_key = cfg.get("api_key") or os.getenv("OPENAI_API_KEY")
    model = cfg.get("model") or DEFAULT_MODEL
    log_calls = bool(cfg.get("log_calls"))
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)
    categories = _load_categories()
    allowed_names = (
        ", ".join(categories.keys())
        if categories
        else "Coding, Docs & Learning, Communication, Meetings, Research, Productivity, Social/Forums, Shopping, Entertainment, Gaming, Utilities, Idle/Unknown"
    )

    system_prompt = f"""You classify computer activity into one of these categories: {allowed_names}.
Return JSON with keys: category (string), productive (boolean), confidence (0-1), rationale (short).
If unsure, use category="Unknown" and productive=false."""

    user_content = {
        "app": app,
        "title": title,
        "url": url,
    }

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_content)},
        ],
        max_tokens=120,
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    message = response.choices[0].message.content
    suggestion = json.loads(message) if message else {}

    if log_calls:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        print("\n===== AI REQUEST (testing) =====")
        print(f"Time: {now}")
        print(json.dumps(user_content, indent=2))
        print("----- AI RESPONSE -----")
        print(message)
        print("===== END AI CALL =====\n")

    # Normalize output
    category = suggestion.get("category") or "Unknown"
    productive = bool(suggestion.get("productive", False))
    confidence = suggestion.get("confidence")
    rationale = suggestion.get("rationale")

    return {
        "category": category,
        "productive": productive,
        "confidence": confidence,
        "rationale": rationale,
    }
