"""The domain-level shapes Search Memory reads/writes/compares — see
docs/03_Data_Model.md `search_requests`/`search_observed_apartments` for the underlying
storage and docs/17_Search_Memory.md for the run-over-run comparison this supports.

These are deliberately distinct from `storage.models.SearchRequestRecord`: that
dataclass mirrors exactly one SQL row; `SearchExecution` is the richer, decoded
business object (parsed `criteria_json`, `runtime_stats` sub-keys promoted to named
fields) that `search_memory_service.py` builds from it — same relationship as
`history.models.Change` vs. `storage.models.ApartmentChangeLogEntry` in v2.0 Step 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SearchExecution:
    """A complete snapshot of one search: what was asked (location/criteria), when, how
    long it took, which platforms were involved, what was found, and where the report
    landed. `pdf_report_path` is always `None` today — no PDF Report Generator exists in
    this codebase (HTML is the only implemented format, docs/09_Report_System.md); the
    field exists so a future PDF export doesn't need another schema change, the same way
    `platforms.connector_version` sat dormant since v2.0 Step 1 until something set it.
    `warnings` is similarly always `[]` for now — reserved for future warning-worthy
    conditions (e.g. a connector returning suspiciously few results) that nothing in the
    pipeline detects yet; not fabricated data.
    """

    id: str
    location: str
    criteria: dict
    created_at: datetime
    label: str | None = None
    execution_time_ms: int | None = None
    discovered_platform_ids: list[str] = field(default_factory=list)
    searched_platform_ids: list[str] = field(default_factory=list)
    failed_platform_ids: list[str] = field(default_factory=list)
    apartment_count: int | None = None
    new_apartment_count: int | None = None
    removed_apartment_count: int | None = None
    changed_apartment_count: int | None = None
    report_path: str | None = None
    pdf_report_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    connector_versions: dict = field(default_factory=dict)
    runtime_stats: dict = field(default_factory=dict)

    @property
    def html_report_path(self) -> str | None:
        """`report_path` *is* the HTML report path — HTML is the only format this
        project generates. A named alias so both "Generated report path" and "HTML
        report path" from the v2.0 Step 3 mission are visible on this model without a
        second, redundant column.
        """
        return self.report_path


@dataclass
class ApartmentPriceChange:
    apartment_id: str
    old_price: float | None
    new_price: float | None


@dataclass
class ApartmentAvailabilityChange:
    apartment_id: str
    old_status: str | None
    new_status: str | None


@dataclass
class PlatformCoverageChange:
    """Which platforms were successfully searched this run that weren't last time, and
    vice versa — distinct from `connector_failures` (which platforms failed *this* run),
    since a platform can stop being searched for reasons other than a failure (e.g. it
    was marked unsupported between runs).
    """

    newly_searched_platform_ids: list[str]
    no_longer_searched_platform_ids: list[str]


@dataclass
class SearchComparison:
    """The structured result of comparing two searches — `CompareSearch(a, b)` from the
    v2.0 Step 3 mission. Deterministic and reproducible: every field is derived purely
    from already-stored history (`search_observed_apartments`, `apartment_price_history`,
    `apartment_availability_history`, `apartment_change_log`), nothing predicted or
    inferred beyond what actually happened.
    """

    previous_search_id: str
    current_search_id: str
    new_apartment_ids: list[str]
    removed_apartment_ids: list[str]
    changed_apartment_ids: list[str]
    price_changes: list[ApartmentPriceChange]
    availability_changes: list[ApartmentAvailabilityChange]
    connector_failures: list[str]
    platform_coverage_change: PlatformCoverageChange
    execution_time_delta_ms: int | None
    search_quality_delta: float | None


@dataclass
class SearchStatistics:
    """Aggregate figures across a location's search history (or every search ever made,
    if `location` is `None`) — `AverageExecutionTime()`/`AverageApartmentCount()`/
    `SearchStatistics()` from the v2.0 Step 3 mission. Plain averages over stored,
    deterministic values — not a prediction or trend model (explicitly out of scope:
    "Do NOT implement AI or predictions").
    """

    location: str | None
    search_count: int
    average_execution_time_ms: float | None
    average_apartment_count: float | None
    average_new_apartment_count: float | None
    average_removed_apartment_count: float | None
    average_changed_apartment_count: float | None


@dataclass
class SearchTimeline:
    """Every search ever made for one location, oldest first — `SearchTimeline()` from
    the v2.0 Step 3 mission. Chronological rather than newest-first (unlike
    `search_history()`) because a timeline is meant to be read in the order things
    happened.
    """

    location: str
    executions: list[SearchExecution]
