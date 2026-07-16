"""Shared shapes for the Continuous Monitoring & Saved Search Engine. See
docs/30_Continuous_Monitoring.md "Architecture".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MonitoringRunStatus(str, Enum):
    """A partial run must remain distinguishable from a complete run (the
    mission's own words) — `PARTIAL` is not a failure, it's an honest "some
    platforms succeeded, some didn't."
    """

    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


# Open-ended by design, same convention `feedback/event_types.py` already
# established for `FeedbackEventType` — "Event types must be extensible ...
# where appropriate" (the mission's own words): a future event type is a new
# string constant plus one `EventDetector`, never a change to this class.
class MonitoringEventType:
    NEW_MATCH = "new_match"
    NEW_LISTING = "new_listing"
    PRICE_DECREASED = "price_decreased"
    PRICE_INCREASED = "price_increased"
    AVAILABILITY_CONFIRMED = "availability_confirmed"
    AVAILABILITY_CHANGED = "availability_changed"
    BECAME_AVAILABLE = "became_available"
    NO_LONGER_AVAILABLE = "no_longer_available"
    LISTING_REMOVED = "listing_removed"
    LISTING_RETURNED = "listing_returned"
    LISTING_UPDATED = "listing_updated"
    IMAGES_CHANGED = "images_changed"
    DESCRIPTION_CHANGED = "description_changed"
    RANK_INCREASED = "rank_increased"
    RANK_DECREASED = "rank_decreased"
    BETTER_MATCH_FOUND = "better_match_found"
    FILTER_MATCH_GAINED = "filter_match_gained"
    FILTER_MATCH_LOST = "filter_match_lost"
    PLATFORM_BECAME_ACCESSIBLE = "platform_became_accessible"
    PLATFORM_BECAME_INACCESSIBLE = "platform_became_inaccessible"
    CONNECTOR_FAILURE = "connector_failure"
    CONNECTOR_RECOVERED = "connector_recovered"
    DISCOVERY_FOUND_NEW_PLATFORM = "discovery_found_new_platform"
    REPORT_GENERATED = "report_generated"
    MONITORING_RUN_FAILED = "monitoring_run_failed"
    MONITORING_RUN_PARTIAL = "monitoring_run_partial"
    MONITORING_RUN_COMPLETED = "monitoring_run_completed"


ALL_EVENT_TYPES = frozenset(
    value for name, value in vars(MonitoringEventType).items() if not name.startswith("_")
)


@dataclass
class MonitoringPolicy:
    """Every configurable knob the mission's own MONITORING POLICY section
    names. No single field has a hardcoded universal default that can't be
    overridden per saved search — "Do not hardcode one universal threshold"
    (the mission's own words) applies to every threshold below.
    """

    manual_only: bool = False
    interval_minutes: int | None = None
    daily_at: str | None = None  # "HH:MM", 24h
    weekly_on: str | None = None  # "monday:HH:MM"
    max_runtime_seconds: int | None = None
    connector_timeout_ms: int | None = None
    max_provider_failures: int | None = None
    retry_policy: dict = field(default_factory=dict)
    minimum_change_significance: float = 0.0
    event_dedup_window_minutes: float = 1440.0
    stale_listing_threshold: int = 1
    removed_listing_threshold: int = 3
    rank_change_significance_threshold: int = 1
    better_match_score_threshold: float = 5.0
    notification_event_types: list[str] = field(default_factory=list)  # empty = every type eligible
    generate_reports: bool = True
    discovery_refresh_before_monitoring: bool = False
    skip_inaccessible_platforms: bool = True
    use_cached_geo: bool = True
    force_fresh_geo: bool = False
    enabled_providers: list[str] | None = None
    disabled_providers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "manual_only": self.manual_only, "interval_minutes": self.interval_minutes,
            "daily_at": self.daily_at, "weekly_on": self.weekly_on,
            "max_runtime_seconds": self.max_runtime_seconds, "connector_timeout_ms": self.connector_timeout_ms,
            "max_provider_failures": self.max_provider_failures, "retry_policy": self.retry_policy,
            "minimum_change_significance": self.minimum_change_significance,
            "event_dedup_window_minutes": self.event_dedup_window_minutes,
            "stale_listing_threshold": self.stale_listing_threshold,
            "removed_listing_threshold": self.removed_listing_threshold,
            "notification_event_types": self.notification_event_types, "generate_reports": self.generate_reports,
            "discovery_refresh_before_monitoring": self.discovery_refresh_before_monitoring,
            "skip_inaccessible_platforms": self.skip_inaccessible_platforms, "use_cached_geo": self.use_cached_geo,
            "force_fresh_geo": self.force_fresh_geo, "enabled_providers": self.enabled_providers,
            "disabled_providers": self.disabled_providers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MonitoringPolicy":
        return cls(**data)


@dataclass
class MonitoringConfiguration:
    """Process/deployment-level knobs, distinct from `MonitoringPolicy` (which
    is per-saved-search behavior) — mirrors `ConnectorConfiguration`/
    `FilterConfiguration`'s own "constructor-level knobs, not per-item policy"
    separation.
    """

    default_claim_ttl_minutes: float = 15.0
    default_worker_id: str = "manual-cli"
    default_policy: MonitoringPolicy = field(default_factory=MonitoringPolicy)


@dataclass
class SavedSearch:
    saved_search_id: str
    name: str
    current_version: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
    profile_id: str | None = None
    description: str | None = None
    id: int | None = None


@dataclass
class SavedSearchVersion:
    """One immutable saved-search definition — "Never overwrite a saved search
    definition. Every modification creates a new SavedSearchVersion" (the
    mission's own words). `request` is exactly `SearchRequest.to_criteria_json()`'s
    own shape (`{"location": ..., "criteria": {...}}`), so a version reproduces
    a real `SearchRequest` directly.
    """

    saved_search_id: str
    version: int
    request: dict
    active_filters: dict
    selected_platforms: list[str]
    selected_connectors: list[str]
    geographic_destinations: list[str]
    monitoring_policy: MonitoringPolicy
    report_options: dict
    retention_policy: dict
    tags: list[str]
    metadata: dict
    created_at: datetime
    ranking_profile: dict | None = None
    feedback_mode: str | None = None
    id: int | None = None


@dataclass
class MonitoringSchedule:
    saved_search_id: str
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None


@dataclass
class MonitoringRun:
    saved_search_id: str
    saved_search_version: int
    started_at: datetime
    status: MonitoringRunStatus = MonitoringRunStatus.RUNNING
    search_id: str | None = None
    completed_at: datetime | None = None
    platforms_attempted: list[str] = field(default_factory=list)
    platforms_succeeded: list[str] = field(default_factory=list)
    platforms_failed: list[str] = field(default_factory=list)
    event_count: int = 0
    notes: str | None = None
    monitoring_run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    id: int | None = None


@dataclass
class MonitoringEvent:
    """One detected change — "Never overwrite events" (the mission's own
    words); every field here is written once, at creation.
    """

    saved_search_id: str
    saved_search_version: int
    monitoring_run_id: str
    event_type: str
    severity: str  # "info" | "warning" | "critical"
    significance: float
    explanation: str
    evidence: dict
    detected_at: datetime
    dedup_key: str
    search_id: str | None = None
    apartment_id: str | None = None
    platform_id: str | None = None
    connector_id: str | None = None
    old_value: dict | None = None
    new_value: dict | None = None
    acknowledged: bool = False
    notification_eligible: bool = True
    metadata: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    id: int | None = None


@dataclass
class RankChange:
    apartment_id: str
    previous_rank: int | None
    current_rank: int | None
    previous_score: float | None
    current_score: float | None

    @property
    def rank_delta(self) -> int | None:
        if self.previous_rank is None or self.current_rank is None:
            return None
        return self.previous_rank - self.current_rank  # positive = moved up (better)

    @property
    def score_delta(self) -> float | None:
        if self.previous_score is None or self.current_score is None:
            return None
        return self.current_score - self.previous_score


@dataclass
class MonitoringComparison:
    """Comparing two monitoring runs for the same saved search. `search_comparison`
    reuses `src.search_memory.models.SearchComparison` directly — apartment-level
    new/removed/price/availability diffing is never reimplemented here.
    """

    previous_monitoring_run_id: str | None
    current_monitoring_run_id: str
    search_comparison: object | None = None  # search_memory.models.SearchComparison | None
    rank_changes: list[RankChange] = field(default_factory=list)
    better_match_apartment_id: str | None = None


@dataclass
class MonitoringStatistics:
    monitoring_run_id: str
    computed_at: datetime
    event_counts_by_type: dict[str, int] = field(default_factory=dict)
    suppressed_duplicate_count: int = 0
    platforms_succeeded_count: int = 0
    platforms_failed_count: int = 0
    average_significance: float | None = None

    def as_dict(self) -> dict:
        return {
            "monitoring_run_id": self.monitoring_run_id, "computed_at": self.computed_at.isoformat(),
            "event_counts_by_type": self.event_counts_by_type,
            "suppressed_duplicate_count": self.suppressed_duplicate_count,
            "platforms_succeeded_count": self.platforms_succeeded_count,
            "platforms_failed_count": self.platforms_failed_count, "average_significance": self.average_significance,
        }


@dataclass
class MonitoringReport:
    """The return value of `report.generate_reports()` — file paths only; the
    HTML/JSON content itself is built from already-stored data, never carried
    in memory here.
    """

    monitoring_run_id: str
    full_html_path: str
    full_json_path: str
    changes_html_path: str
    changes_json_path: str
    generated_at: datetime


@dataclass
class MonitoringHealth:
    """One saved search's operational health — mirrors `ConnectorHealth`/
    `ProviderHealth`'s own "observed, not predicted" shape.
    """

    saved_search_id: str
    enabled: bool
    last_run_status: str | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    is_claimed: bool
    claim_expires_at: datetime | None
    consecutive_failure_count: int

    @property
    def is_healthy(self) -> bool:
        return self.consecutive_failure_count == 0
