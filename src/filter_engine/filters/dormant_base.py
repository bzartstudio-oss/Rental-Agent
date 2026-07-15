"""Shared base classes for **dormant** filters — every filter in `amenities.py`/
`preferences_and_other.py` whose mission-specified field doesn't exist anywhere in
`Apartment`/`RawListing`/`SearchRequest` yet. See
docs/25_Dynamic_Filter_Engine.md "Dormant Filters" for the full reasoning.

Every dormant filter's `apply()` always returns `True` — "no evidence to exclude on"
is never treated as "excluded," the same convention `RawListing`'s honest `None`
fields and the Analysis Engine's `score=None` already established repeatedly
throughout this project. `validate()` still checks the *value*'s own shape (a
boolean filter still rejects a non-boolean value), so a malformed request is caught
even though the field itself can't be evaluated yet — a dormant filter is honestly
inert, not silently permissive of garbage input.

Most of these map directly onto the "room/flatshare filter categories" tension
flagged and deliberately deferred throughout this project's history (gender,
room_type, private_bathroom, student_only — see `learning/architecture_notes.md`'s
2026-07-14 entry and the SDK Validation Sprint's Finding 1, docs/22) — building real
data support for them is a product-scope decision this sprint doesn't make, not an
oversight.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.filter_engine.base_filter import BaseFilter, FilterContext
from src.storage.models import Apartment

DORMANT_NOTE = (
    "Dormant: no backing field exists on Apartment/RawListing yet, so this filter "
    "always passes (never excludes) regardless of the value given. See "
    "docs/25_Dynamic_Filter_Engine.md 'Dormant Filters'."
)


class _DormantFilter(BaseFilter):
    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        return True


class DormantBooleanFilter(_DormantFilter):
    def validate(self, value: Any) -> None:
        if not isinstance(value, bool):
            raise ValueError(f"expected a boolean, got {value!r}")


class DormantStringFilter(_DormantFilter):
    def validate(self, value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"expected a non-empty string, got {value!r}")


class DormantNumberFilter(_DormantFilter):
    def validate(self, value: Any) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"expected a non-negative number, got {value!r}")


class DormantDateFilter(_DormantFilter):
    def validate(self, value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"expected an ISO 8601 date string, got {value!r}")
        date.fromisoformat(value)  # raises ValueError itself for a malformed date
