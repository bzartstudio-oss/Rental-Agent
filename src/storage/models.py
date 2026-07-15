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
    # v2.0 Step 7 (migration 0004) — no reference connector had real data for these;
    # the first production connector (RentCast) does. See docs/20_First_Production_Connector.md.
    currency: str | None = None
    property_type: str | None = None


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
class PlatformPerformanceObservation:
    """Mirrors one row of `platform_performance_observations` (docs/03_Data_Model.md) —
    added in migration 0001, given real read/write logic in v2.0 Step 4. See
    docs/16_Knowledge_Engine.md for what each metric means and how it's computed. One
    row per (platform, search) — including failed searches ("Learning From Failure"):
    `failed=True` still gets a row, with `results_count=0` and most quality scores `None`.
    """

    platform_id: str
    search_id: str
    results_count: int
    failed: bool
    parsing_success: bool
    observed_at: datetime
    response_time_ms: int | None = None
    extraction_quality_score: float | None = None
    image_quality_score: float | None = None
    availability_quality_score: float | None = None
    duplicate_rate: float | None = None
    ranking_usefulness_score: float | None = None
    id: int | None = None


@dataclass
class ApartmentAnalysisMetric:
    """Mirrors one row of `apartment_analysis_metrics` (docs/03_Data_Model.md) — added in
    migration 0001, given real read/write logic in v2.0 Step 6. Generic key/value so a
    new metric type never needs a schema migration: `metric_name` identifies which
    analyzer/metric this is (e.g. `"walking_distance"`, `"composite:location_score"`),
    `metric_value` is that analyzer's score. `confidence`/`evidence_json`/
    `analyzer_version` were added in migration 0003, once the Deep Analysis Engine's
    richer `AnalyzerResult` shape (Score/Confidence/Evidence/Timestamp/Version/Source)
    needed more than the four columns migration 0001 originally designed.

    Never written when there's no evidence to score (`metric_value` is `NOT NULL`) —
    see `src/analysis/analysis_service.py`. Append-only like everything else in this
    system: a metric that changes gets a new row, never an overwrite.
    """

    apartment_id: str
    metric_name: str
    metric_value: float
    source_module: str
    computed_at: datetime
    metric_unit: str | None = None
    search_id: str | None = None
    confidence: float | None = None
    evidence: list[str] | None = None
    warnings: list[str] | None = None
    analyzer_version: str | None = None
    id: int | None = None


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


@dataclass
class FilterDefinitionRecord:
    """Mirrors one row of `filter_definitions` (migration 0001) — designed for the
    Dynamic Filter Engine and left unused until v2.5 Step 9 gave it real read/write
    logic. One row per registered `BaseFilter`, kept in sync via
    `filter_engine.sync_filter_definitions()`.
    """

    key: str
    display_name: str
    category: str
    value_type: str
    applicable_rental_types: list[str]
    created_at: datetime
    description: str | None = None


@dataclass
class FilterExecutionHistoryEntry:
    """Mirrors one row of `filter_execution_history` (migration 0005, v2.5 Step 9) —
    one row per `FilterEngine.run()` call, append-only like every other history table
    in this system.
    """

    search_id: str
    filter_set: dict
    total_apartments: int
    matched_count: int
    statistics: dict
    recorded_at: datetime
    execution_time_ms: int | None = None
    id: int | None = None


@dataclass
class GeoEnrichmentHistoryEntry:
    """Mirrors one row of `geo_enrichment_history` (migration 0006, v2.5 Step 10) —
    one row per `GeographicEngine.enrich()` call, append-only like every other
    history table in this system.
    """

    apartment_id: str
    provider_id: str
    calculation_method: str
    summary: dict
    confidence: float | None
    recorded_at: datetime
    search_id: str | None = None
    id: int | None = None
