"""`to_jsonable()` — the one recursive converter every `api/` module uses to
turn a dataclass/enum/datetime/Path graph into plain JSON-safe Python. See
docs/32_Web_Dashboard.md "API Structure".

Centralized so no individual API endpoint reinvents dataclass-to-dict
serialization (and risks doing it slightly differently each time).
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import date, datetime
from pathlib import Path


def to_jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    return str(value)
