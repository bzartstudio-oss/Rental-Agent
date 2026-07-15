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
    """A known rental platform, managed by the Multi-Platform Discovery Framework
    (docs/05_Platform_Discovery.md). `connector_available` distinguishes a platform this
    system can actually search from one that's merely catalogued.
    """

    id: str
    name: str
    country: str
    homepage: str
    connector_available: bool = False
    supported_cities: list[str] = field(default_factory=list)
    rental_types: list[str] = field(default_factory=list)
    search_url: str | None = None
    requires_login: bool = False
    connector_name: str | None = None
    last_verified: datetime | None = None
    discovery_method: str = "manual"
    notes: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    # v2.0 (migration 0001) — Platform Intelligence rollups, docs/05_Platform_Discovery.md.
    # Computed by the Knowledge Engine (not built yet); always None until that logic exists.
    connector_version: str | None = None
    reliability_score: float | None = None
    success_rate: float | None = None
    avg_response_time_ms: float | None = None
    avg_apartment_count: float | None = None
    duplicate_percentage: float | None = None


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
    # v2.0 (migration 0001) — required before its changes can be tracked in
    # apartment_change_log; not yet populated by normalizer.py (docs/07_Analysis_Engine.md).
    description: str | None = None


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
    # v2.0 (migration 0001) — docs/03_Data_Model.md. is_current=False means this image
    # was removed from the listing on a later observation but stays on disk/in the table
    # (Principle 1) — see apartment_image_events for the add/remove log itself.
    thumbnail_path: str | None = None
    is_current: bool = True


@dataclass
class ApartmentChangeLogEntry:
    """Mirrors one row of `apartment_change_log` (docs/03_Data_Model.md) — the generic
    history table for title/description/coordinates and any future free-text/simple
    field, added in migration 0001 and given real read/write logic in v2.0 Step 2
    (src/history/). `old_value=None` marks the field's first-ever observation.
    """

    apartment_id: str
    field_name: str
    new_value: str
    observed_at: datetime
    old_value: str | None = None
    search_id: str | None = None
    id: int | None = None


@dataclass
class ApartmentImageEvent:
    """Mirrors one row of `apartment_image_events` (docs/03_Data_Model.md) — added in
    migration 0001, given real read/write logic in v2.0 Step 2. `event` is `"added"` or
    `"removed"`; `search_id` is NOT NULL in the schema (an image event is always tied to
    the search run that detected it — unlike price/availability history, which can be
    written without one).
    """

    apartment_id: str
    event: str
    source_url: str
    search_id: str
    observed_at: datetime
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
    # v2.0 (migration 0001) — Search Memory, docs/17_Search_Memory.md. All None until a
    # run completes and RentalResearchAgent.run() is updated to fill them in (not this sprint).
    execution_time_ms: int | None = None
    discovered_platform_ids: list[str] | None = None
    searched_platform_ids: list[str] | None = None
    apartment_count: int | None = None
    new_apartment_count: int | None = None
    removed_apartment_count: int | None = None
    changed_apartment_count: int | None = None
    report_path: str | None = None
    runtime_stats: dict | None = None


@dataclass
class SearchObservedApartment:
    """Mirrors one row of `search_observed_apartments` (docs/03_Data_Model.md) — added in
    migration 0001, given real read/write logic in v2.0 Step 3. The **full** set of
    apartments a search processed, independent of `search_results`' ranked/filtered
    subset — this is what run-over-run comparison (`src/search_memory/`) diffs, so
    "removed" means "gone from the platform," not "excluded by this run's filters."
    """

    search_id: str
    apartment_id: str
    observed_at: datetime
    id: int | None = None


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
