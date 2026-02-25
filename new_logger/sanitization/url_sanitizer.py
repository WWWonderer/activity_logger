# sanitizer.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


# -----------------------------
# regex heuristics
# -----------------------------

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)                                                    # eg. 550e8400-e29b-41d4-a716-446655440000
HEX_RE = re.compile(r"^[0-9a-fA-F]{16,}$")           # eg. a3f1b9c4d8e7f123
B64URL_RE = re.compile(r"^[A-Za-z0-9_-]{24,}$")      # eg. 4f3GhT-2Lk8vPq9sXzA1BcDeF
JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$") # eg. john@example.com

# Keys that are almost always sensitive: redact values.
SENSITIVE_KEY_SUBSTRINGS = (
    "pass", "password", "pwd",
    "token", "access_token", "refresh_token", "serviceToken", "id_token", "session", "auth",
    "key", "api_key", "secret", "signature", "sig",
    "code", "otp", "pin", "assertion",
    "cookie", "jwt", "saml",
    "email", "phone", "user", "username",
    "redirect", "return", "next", "continue",
)

# A tiny, readable guardrail: don't store huge values.
MAX_VALUE_LEN = 128
COMPACT_SECRET_MIN_LEN = 48


@dataclass(frozen=True)
class SanitizeResult:
    sanitized_url: str
    dropped_fragment: bool
    redacted_keys: Tuple[str, ...]


def sanitize_url(url: str) -> SanitizeResult:
    """
    - Drops fragment
    - Drops userinfo (user:pass@)
    - Keeps scheme + hostname (lowercased)
    - Sanitizes path segments (IDs -> placeholders)
    - Query params:
        * redact value if key is sensitive
        * also redact value if the value itself looks sensitive (token/email/jwt/etc.)
        * otherwise keep the value (capped)
    """
    parts = urlsplit(url)

    # --- Authority (netloc): drop userinfo, keep host:port
    hostname = (parts.hostname or "").lower()
    port = parts.port
    netloc = hostname
    if port is not None:
        netloc = f"{hostname}:{port}"

    # --- Fragment: always drop (but record whether it existed)
    dropped_fragment = bool(parts.fragment)

    # --- Path: sanitize segments
    sanitized_path = _sanitize_path(parts.path)

    # --- Query: conditionally redact
    query_items = parse_qsl(parts.query, keep_blank_values=True)

    redacted_keys: List[str] = []
    sanitized_query_items: List[Tuple[str, str]] = []

    for k, v in query_items:
        key = (k or "").strip()
        if not key:
            continue

        val = "" if v is None else v.strip()

        if _is_sensitive_key(key) or _value_is_sensitive(val):
            redacted_keys.append(key)
            sanitized_query_items.append((key, "_REDACTED_"))
        else:
            sanitized_query_items.append((key, _cap_value(val)))

    # Sort keys for stability (helps classification + dedup)
    sanitized_query_items.sort(key=lambda kv: kv[0].lower())

    sanitized_query = urlencode(sanitized_query_items, doseq=True)

    # print(f'sanitized_path: {sanitized_path}')
    # print(f'sanitized_query: {sanitized_query}')

    sanitized = urlunsplit((
        parts.scheme.lower() if parts.scheme else "http",
        netloc,
        sanitized_path,
        sanitized_query,
        ""  # fragment removed
    ))

    return SanitizeResult(
        sanitized_url=sanitized,
        dropped_fragment=dropped_fragment,
        redacted_keys=tuple(sorted(set(redacted_keys), key=str.lower)),
    )


# -----------------------------
# Helpers
# -----------------------------

def _sanitize_path(path: str) -> str:
    if not path:
        return "/"
    segments = [s for s in path.split("/") if s != ""]
    out: List[str] = []
    for seg in segments:
        out.append(_segment_placeholder(seg))
    return "/" + "/".join(out)


def _segment_placeholder(seg: str) -> str:
    s = seg.strip()
    if not s:
        return ""

    if s.isdigit():
        return "[INT]"
    if UUID_RE.match(s):
        return "[UUID]"
    if EMAIL_RE.match(s):
        return "[EMAIL]"
    if JWT_RE.match(s):
        return "[JWT]"
    if HEX_RE.match(s) or B64URL_RE.match(s):
        return "[ID]"
    if len(s) > 64:
        return "[TEXT_LONG]"
    return s


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(sub in k for sub in SENSITIVE_KEY_SUBSTRINGS)


def _value_is_sensitive(val: str) -> bool:
    """
    Redact values that look like secrets/PII even if the key name is innocent.
    This prevents leaks like ?q=<jwt> or ?id=<token>.
    """
    if not val:
        return False

    if EMAIL_RE.match(val):
        return True
    if JWT_RE.match(val):
        return True
    if UUID_RE.match(val):
        return True
    if HEX_RE.match(val):
        return True
    if B64URL_RE.match(val):
        return True

    if _looks_like_embedded_http_url(val):
        return True

    if _looks_like_compact_secret(val):
        return True

    # Very long values are risky (often tokens or embedded data)
    if len(val) > MAX_VALUE_LEN:
        return True

    return False


def _cap_value(val: str) -> str:
    if len(val) <= MAX_VALUE_LEN:
        return val
    return val[:MAX_VALUE_LEN] + "…"

def _looks_like_embedded_http_url(val: str) -> bool:
    decoded = _decode_percent_escapes(val)
    parts = urlsplit(decoded)
    return parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)

def _decode_percent_escapes(s: str, rounds: int = 2) -> str:
    current = s
    for _ in range(rounds):
        decoded = unquote(current)
        if decoded == current:
            break
        current = decoded
    return current


def _looks_like_compact_secret(val: str) -> bool:
    if len(val) < COMPACT_SECRET_MIN_LEN:
        return False
    if any(ch.isspace() for ch in val):
        return False

    classes = 0
    if any(ch.islower() for ch in val):
        classes += 1
    if any(ch.isupper() for ch in val):
        classes += 1
    if any(ch.isdigit() for ch in val):
        classes += 1
    if any(not ch.isalnum() for ch in val):
        classes += 1

    # Long compact values with mixed classes are commonly secrets/tokens.
    return classes >= 3
