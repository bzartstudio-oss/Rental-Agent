"""Shared low-level parsing/validation helpers every form module builds on.
See docs/32_Web_Dashboard.md "Validation".
"""

from __future__ import annotations

import re
from datetime import date, datetime

from src.web.error_handler import WebValidationError
from src.web.security import WebSecurity

_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")
_MAX_RESULT_LIMIT = 200


def require_text(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise WebValidationError(f"{field_name} is required")
    return value.strip()


def parse_safe_id(value: str | None, field_name: str) -> str:
    """Rejects a malformed id outright — including any path-traversal
    attempt (`../`, absolute paths, null bytes) — before it ever reaches a
    repository lookup or a file path built from it.
    """
    value = require_text(value, field_name)
    if not _ID_RE.match(value) or ".." in value:
        raise WebValidationError(f"{field_name} contains characters that are not allowed")
    return value


def parse_optional_float(value: str | None, field_name: str, *, minimum: float | None = None) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        raise WebValidationError(f"{field_name} must be a number") from None
    if minimum is not None and parsed < minimum:
        raise WebValidationError(f"{field_name} must be at least {minimum}")
    return parsed


def parse_optional_int(value: str | None, field_name: str, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError:
        raise WebValidationError(f"{field_name} must be a whole number") from None
    if minimum is not None and parsed < minimum:
        raise WebValidationError(f"{field_name} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise WebValidationError(f"{field_name} must be at most {maximum}")
    return parsed


def parse_result_limit(value: str | None, *, default: int = 50) -> int:
    limit = parse_optional_int(value, "Maximum result count", minimum=1, maximum=_MAX_RESULT_LIMIT)
    return limit if limit is not None else default


def parse_optional_date(value: str | None, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise WebValidationError(f"{field_name} must be a valid date (YYYY-MM-DD)") from None


def parse_bool(value: str | None) -> bool:
    return value is not None and value.lower() in {"on", "true", "1", "yes"}


def parse_checkbox_list(values: list[str]) -> list[str]:
    return [v for v in values if v]


def parse_ranking_weights(form) -> dict[str, float] | None:
    """`ranking_weight__<rule_key>` fields, present only when the user chose
    "custom" ranking priorities — absent entirely means "use the default
    profile," never a fabricated all-zero weight set.
    """
    weights: dict[str, float] = {}
    for key in form:
        if not key.startswith("ranking_weight__"):
            continue
        rule_key = key[len("ranking_weight__"):]
        value = parse_optional_float(form.get(key), f"Ranking weight for {rule_key}", minimum=0.0)
        if value is not None:
            weights[rule_key] = value
    return weights or None


def parse_safe_url(value: str | None, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    if not WebSecurity.is_safe_url(value):
        raise WebValidationError(f"{field_name} must be a valid http(s) URL")
    return value
