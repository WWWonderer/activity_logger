import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "category_rules.json"
KEYWORD_INDEX_PATH = Path(__file__).resolve().parent.parent / "config" / "keyword_index.json"
KEYWORDS_PER_CATEGORY = 500
KEYWORD_SESSION_RESET_SECONDS = 120

AMBIGUOUS_DOMAINS = {
    "www.google.com",
    "google.com",
    "www.bing.com",
    "bing.com",
    "www.chatgpt.com",
    "chatgpt.com",
}

# Apps treated as browsers for AI-keying and rule updates
BROWSER_APPS = {
    "chrome",
    "google chrome",
    "firefox",
    "mozilla firefox",
    "safari",
    "edge",
    "microsoft edge",
    "brave",
    "arc",
    "opera",
    "vivaldi",
}


def _load_rules(rules_path=CONFIG_PATH):
    return json.loads(Path(rules_path).read_text())


CATEGORY_RULES = _load_rules()


def _save_rules(rules, rules_path=CONFIG_PATH):
    Path(rules_path).write_text(json.dumps(rules, indent=2))
    global CATEGORY_RULES
    CATEGORY_RULES = rules
    _rebuild_indexes(rules)

def _build_indexes(rules):
    """
    Precompute lookup maps for O(1) app and host matches, and small-per-host path checks.
    """
    app_index = {}
    domain_index = {}

    for category, data in rules.items():
        productive_flag = bool(data.get("productive", False))

        for token in data.get("apps", []):
            token = token.strip().lower()
            if token:
                app_index[token] = (category, productive_flag)

        for token in data.get("domains", []):
            token = token.strip().lower()
            if not token:
                continue
            host, sep, path = token.partition("/")
            host = host.strip()
            if not host:
                continue
            path = path.strip()
            if sep and path and not path.startswith("/"):
                path = "/" + path
            domain_index.setdefault(host, []).append((path, category, productive_flag))

    # More specific paths first
    for host, paths in domain_index.items():
        domain_index[host] = sorted(paths, key=lambda p: len(p[0]), reverse=True)

    return app_index, domain_index
APP_INDEX, DOMAIN_INDEX = _build_indexes(CATEGORY_RULES)
AI_CACHE = {}
KEYWORD_AI_CACHE = {}

def _load_keyword_index(index_path=None):
    index_path = index_path or KEYWORD_INDEX_PATH
    if not Path(index_path).exists():
        return {}
    try:
        return json.loads(Path(index_path).read_text())
    except Exception:
        return {}


def _save_keyword_index(index, index_path=None):
    index_path = index_path or KEYWORD_INDEX_PATH
    Path(index_path).write_text(json.dumps(index, indent=2))
    global KEYWORD_INDEX, KEYWORD_LOOKUP
    KEYWORD_INDEX = index
    KEYWORD_LOOKUP = _build_keyword_lookup(index)


def _build_keyword_lookup(index):
    lookup = {}
    for category, entries in index.items():
        for entry in entries:
            keyword = entry.get("keyword", "").strip().lower()
            if keyword and keyword not in lookup:
                productive = CATEGORY_RULES.get(category, {}).get("productive", False)
                lookup[keyword] = (category, productive)
    return lookup


KEYWORD_INDEX = _load_keyword_index()
KEYWORD_LOOKUP = _build_keyword_lookup(KEYWORD_INDEX)
KEYWORD_SESSION_STATE = {}


def _rebuild_indexes(rules):
    global APP_INDEX, DOMAIN_INDEX
    APP_INDEX, DOMAIN_INDEX = _build_indexes(rules)


def _record_keyword_session_hit(context_key, category, keyword):
    """
    Increment keyword count once per session (context + keyword). Resets after timeout or change.
    """
    if not context_key or not keyword:
        return
    now = time.time()
    prev = KEYWORD_SESSION_STATE.get(context_key)
    if prev:
        prev_keyword = prev.get("keyword")
        last_seen = prev.get("ts", 0)
        if prev_keyword == keyword and (now - last_seen) < KEYWORD_SESSION_RESET_SECONDS:
            KEYWORD_SESSION_STATE[context_key]["ts"] = now
            return
    _increment_keyword_count(category, keyword)
    KEYWORD_SESSION_STATE[context_key] = {"keyword": keyword, "ts": now}


def _increment_keyword_count(category, keyword):
    """
    Add or increment a keyword within its category, respecting the per-category cap.
    """
    if not keyword:
        return
    keyword = keyword.strip().lower()
    if not keyword:
        return

    entries = KEYWORD_INDEX.setdefault(category, [])
    for idx, entry in enumerate(entries):
        if entry.get("keyword") == keyword:
            entry["count"] = entry.get("count", 0) + 1
            _save_keyword_index(KEYWORD_INDEX)
            return

    if len(entries) < KEYWORDS_PER_CATEGORY:
        entries.append({"keyword": keyword, "count": 1})
        print(f'Adding {keyword} to keyword index...')
    else:
        min_idx = min(range(len(entries)), key=lambda i: (entries[i].get("count", 0), i))
        print(f'Removing {entries[min_idx]} from keyword index, adding {keyword} to index...')
        entries[min_idx] = {"keyword": keyword, "count": 1}
    _save_keyword_index(KEYWORD_INDEX)


def _match_keyword_index(normalized_title, context_key=None):
    for keyword in _extract_keyword_candidates(normalized_title):
        keyword_lower = keyword.lower()
        if keyword_lower in KEYWORD_LOOKUP:
            category, productive_flag = KEYWORD_LOOKUP[keyword_lower]
            _record_keyword_session_hit(context_key, category, keyword_lower)
            return category, productive_flag
    return None


def categorize(app, title, url, context_key=None):
    """
    Rule-based classifier. Categories are deterministic; each has a boolean productive flag.

    Matching priority per category (in file order):
    1) app tokens
    2) domain/path tokens (host + path without query/fragment)
    3) keyword index (ambiguous hosts or unknowns)
    """
    normalized_app = (app or "").lower()
    normalized_title = (title or "").lower()
    parsed = urlparse(url or "")
    host_lower = (parsed.hostname or "").lower()
    path_lower = (parsed.path or "").lower()

    if normalized_app == "idle" or normalized_title == "idle":
        return "Idle", False

    # App match (exact token)
    if normalized_app in APP_INDEX:
        return APP_INDEX[normalized_app]

    # Domain + optional path prefix match
    domain_match = _match_domain(host_lower, path_lower)
    if domain_match:
        category, productive_flag = domain_match
        if host_lower in AMBIGUOUS_DOMAINS:
            keyword_match = _match_keyword_index(normalized_title, context_key=context_key)
            if keyword_match:
                return keyword_match
        return category, productive_flag

    # keyword match
    keyword_match = _match_keyword_index(normalized_title, context_key=context_key)
    if keyword_match:
        return keyword_match

    return "Unknown", False


def _match_domain(host_lower, path_lower):
    """
    Match exact host and most specific path prefix (if provided in rules).
    """
    if not host_lower:
        return None
    for path_prefix, category, productive_flag in DOMAIN_INDEX.get(host_lower, []):
        if path_prefix:
            if path_lower.startswith(path_prefix):
                return category, productive_flag
        else:
            return category, productive_flag
    return None


def _extract_keyword(title):
    """
    Pull a simple keyword from the title to disambiguate ambiguous domains.
    """
    words = re.split(r"[^a-z0-9]+", (title or "").lower())
    words = [w for w in words if len(w) >= 4]
    if not words:
        return None
    return " ".join(words[:2])


def _extract_keyword_candidates(title):
    """
    Generate plausible keyword phrases from a title to improve matches.
    """
    words = re.split(r"[^a-z0-9]+", (title or "").lower())
    words = [w for w in words if len(w) >= 4]
    if not words:
        return []

    candidates = []
    if len(words) >= 2:
        candidates.append(" ".join(words[:2]))   # leading phrase
        candidates.append(" ".join(words[-2:]))  # trailing phrase
    else:
        candidates.append(words[0])

    seen = set()
    deduped = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def _ai_cache_key(app, host_lower, title):
    """
    Deterministic cache key to avoid repeated AI calls:
     - Browsers: use host (and keyword for ambiguous hosts).
     - Non-browsers: use app name.
     - Fallback to host or "unknown".
    """
    app_norm = (app or "").strip().lower()
    if (app_norm in BROWSER_APPS or not app_norm) and host_lower:
        if host_lower in AMBIGUOUS_DOMAINS:
            keyword = _extract_keyword(title)
            return f"{host_lower}|{keyword}" if keyword else host_lower
        return host_lower
    return app_norm or host_lower or "unknown"


def _add_rule_from_ai(category, productive, app, title, url):
    """
    Update category_rules.json in-place with the AI result.

    - Browser/URL: add domain rule (skip ambiguous hosts to avoid over-broad rules).
    - Non-browser app: add app rule.
    """
    global CATEGORY_RULES
    rules = CATEGORY_RULES
    cat_rules = rules.setdefault(
        category, {"apps": [], "domains": [], "productive": bool(productive)}
    )
    cat_rules.setdefault("apps", [])
    cat_rules.setdefault("domains", [])
    if "productive" not in cat_rules:
        cat_rules["productive"] = bool(productive)

    parsed = urlparse(url or "")
    host_lower = (parsed.hostname or "").lower()
    app_norm = (app or "").lower()

    if (app_norm in BROWSER_APPS or not app_norm) and host_lower:
        if host_lower not in AMBIGUOUS_DOMAINS:
            existing_domains = [d.lower() for d in cat_rules.get("domains", [])]
            if host_lower not in existing_domains:
                cat_rules["domains"].append(host_lower)
                print(f'saving {host_lower} to {category}...')
    elif app_norm and app_norm not in BROWSER_APPS:
            existing_apps = [a.lower() for a in cat_rules.get("apps", [])]
            if app_norm not in existing_apps:
                cat_rules["apps"].append(app_norm)
                print(f'saving {app_norm} to {category}...')
    _save_rules(rules)


def categorize_with_ai(app, title, url, ai_callback=None):
    """
    Rule-based categorization with optional AI fallback.

    ai_callback should accept (app, title, url) and return a dict like:
    {"category": "X", "productive": True/False, "confidence": 0.8, "rationale": "..."}

    Example: from logger.ai_callback import openai_categorize; pass ai_callback=openai_categorize
    """
    global KEYWORD_LOOKUP
    parsed = urlparse(url or "")
    host_lower = (parsed.hostname or "").lower()
    cache_key = _ai_cache_key(app, host_lower, title)

    # 
    category, productive = categorize(app, title, url, context_key=cache_key)

    keyword_candidates = _extract_keyword_candidates(title)
    keyword_lower = keyword_candidates[0].lower() if keyword_candidates else None
    needs_keyword_ai = keyword_lower and (
        host_lower in AMBIGUOUS_DOMAINS or category == "Unknown"
    )

    if not needs_keyword_ai:
        return category, productive

    for candidate in keyword_candidates:
        cand_lower = candidate.lower()
        if cand_lower in KEYWORD_LOOKUP:
            cat, prod = KEYWORD_LOOKUP[cand_lower]
            _record_keyword_session_hit(cache_key, cat, cand_lower)
            return cat, prod
        if cand_lower in KEYWORD_AI_CACHE:
            cat, prod = KEYWORD_AI_CACHE[cand_lower]
            _record_keyword_session_hit(cache_key, cat, cand_lower)
            return cat, prod

    if keyword_lower is None:
        return category, productive

    if ai_callback is None:
        return category, productive

    try:
        suggestion = ai_callback(app=app, title=title, url=url) or {}
    except Exception:
        AI_CACHE[cache_key] = (category, productive)
        return category, productive

    suggested_category = suggestion.get("category", "Unknown")
    suggested_productive = bool(suggestion.get("productive", False))

    if suggested_category != "Unknown":
        KEYWORD_AI_CACHE[keyword_lower] = (suggested_category, suggested_productive)
        _increment_keyword_count(suggested_category, keyword_lower)
        KEYWORD_LOOKUP = _build_keyword_lookup(KEYWORD_INDEX)
        _record_keyword_session_hit(cache_key, suggested_category, keyword_lower)
        if host_lower not in AMBIGUOUS_DOMAINS:
            _add_rule_from_ai(suggested_category, suggested_productive, app, title, url)
        AI_CACHE[cache_key] = (suggested_category, suggested_productive)
        return suggested_category, suggested_productive

    AI_CACHE[cache_key] = (category, productive)
    return category, productive


# TODO: can use a classification model for unknown front apps
