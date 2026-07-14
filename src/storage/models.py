"""Dataclasses mirroring the tables in schema.sql — see docs/03_Data_Model.md for the
design rationale behind each field. One dataclass per table, same names, same shape,
so a repository function's input/output type is always obviously "one row of table X".

Timestamps are `datetime` here (not `str`) so callers can compare/format them normally —
converting to/from the ISO 8601 strings the database actually stores is the repository
layer's job, not something every caller should have to do by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    """`datetime.utcnow()` is deprecated (Python 3.12+) in favor of a timezone-aware
    call — using this everywhere keeps every default timestamp in this module consistent.
    """
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """datetime -> the TEXT format every timestamp column in schema.sql stores."""
    return dt.isoformat()


def parse_iso(value: str) -> datetime:
    """The inverse of iso() — every repository read goes through this so callers always
    get a real datetime back, never a raw string.
    """
    return datetime.fromisoformat(value)


@dataclass
class Platform:
    id: str
    name: str
    base_url: str
    connector_module: str
    is_active: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    notes: str | None = None


@dataclass
class Apartment:
    id: str
    platform_id: str
    platform_listing_id: str
    title: str
    url: str
    current_price: float
    current_status: str
    first_seen_at: datetime
    last_seen_at: datetime
    bedrooms: float | None = None
    bathrooms: float | None = None
    sqft: float | None = None
    address_raw: str | None = None
    address_normalized: dict | None = None
    latitude: float | None = None
    longitude: float | None = None
    merged_into_id: str | None = None  # unused in V1 — reserved for V2 cross-platform dedup


@dataclass
class ApartmentPriceHistoryEntry:
    apartment_id: str
    price: float
    observed_at: datetime
    search_id: str | None = None
    id: int | None = None  # None until persisted (AUTOINCREMENT assigns it)


@dataclass
class ApartmentAvailabilityHistoryEntry:
    apartment_id: str
    status: str
    observed_at: datetime
    search_id: str | None = None
    id: int | None = None


@dataclass
class ApartmentImage:
    apartment_id: str
    source_url: str
    local_path: str
    downloaded_at: datetime
    position: int = 0
    id: int | None = None


@dataclass
class SearchRequestRecord:
    """The persisted form of a SearchRequest (see search/search_request.py for the
    richer domain object this is built from) — just enough to satisfy Principle 4
    (every search is reproducible): the exact criteria it was run with.
    """

    id: str
    created_at: datetime
    criteria_json: str
    label: str | None = None


@dataclass
class SearchResultEntry:
    """One ranked apartment within one search run. price_at_search/status_at_search
    are a deliberate snapshot, not a live join — see docs/03_Data_Model.md.
    """

    search_id: str
    apartment_id: str
    rank: int
    score: float
    score_breakdown_json: str
    price_at_search: float
    status_at_search: str
    id: int | None = None


@dataclass
class KnowledgeEntry:
    category: str
    key: str
    value_json: str
    updated_at: datetime
    source: str | None = None
    id: int | None = None


@dataclass
class RawCapture:
    platform_id: str
    search_id: str
    raw_page_path: str
    captured_at: datetime
    apartment_id: str | None = None  # null until the Analysis Engine resolves this capture
    id: int | None = None
