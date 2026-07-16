"""Shared shapes for the Automatic Platform Discovery Agent. See
docs/29_Automatic_Platform_Discovery.md "Architecture".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PlatformStatus(str, Enum):
    """The mission's own 12 statuses. A discovered platform never automatically
    becomes research-active — see docs/29 "Registry Integration": activation
    requires an available certified connector or an explicitly approved API/feed
    integration, regardless of status here.
    """

    DISCOVERED = "discovered"
    VERIFIED = "verified"
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    DUPLICATE = "duplicate"
    INACCESSIBLE = "inaccessible"
    REQUIRES_LOGIN = "requires_login"
    REQUIRES_MANUAL_REVIEW = "requires_manual_review"
    CONNECTOR_AVAILABLE = "connector_available"
    CONNECTOR_MISSING = "connector_missing"
    UNSUPPORTED = "unsupported"
    DISABLED = "disabled"


class PlatformClassification(str, Enum):
    """The mission's own 13 categories. Assigned deterministically from evidence
    keywords — see `src.discovery.automatic.classification` — never an opaque
    model.
    """

    RENTAL_MARKETPLACE = "rental_marketplace"
    PROPERTY_PORTAL = "property_portal"
    SHARED_HOUSING_PLATFORM = "shared_housing_platform"
    STUDENT_HOUSING_PLATFORM = "student_housing_platform"
    LOCAL_AGENCY = "local_agency"
    PROPERTY_MANAGER = "property_manager"
    AGGREGATOR = "aggregator"
    CLASSIFIEDS = "classifieds"
    SOCIAL_OR_COMMUNITY_SOURCE = "social_or_community_source"
    COMMERCIAL_PROPERTY_PLATFORM = "commercial_property_platform"
    VACATION_RENTAL_PLATFORM = "vacation_rental_platform"
    IRRELEVANT = "irrelevant"
    UNKNOWN = "unknown"


@dataclass
class DiscoveryPolicy:
    """Governs whether a fresh discovery run is even needed for a given request —
    "Determine whether refresh is required" (the mission's own workflow step).
    A real, configurable policy, not a hidden constant.
    """

    max_age_days: float = 30.0
    force_refresh: bool = False


@dataclass
class DiscoveryRequest:
    """Every field the mission's DISCOVERY REQUEST section names, optional where
    practical — a request naming only `city` is just as valid as one naming
    everything.
    """

    country: str | None = None
    region: str | None = None
    city: str | None = None
    postal_area: str | None = None
    language: str | None = None
    rental_categories: list[str] = field(default_factory=list)
    property_types: list[str] = field(default_factory=list)
    room_or_shared_housing_intent: bool = False
    long_or_short_term: str | None = None  # "long_term" | "short_term" | None
    student_housing: bool = False
    professional_housing: bool = False
    commercial_rental: bool = False
    max_candidates: int = 50
    allowed_domains: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)
    refresh_policy: DiscoveryPolicy = field(default_factory=DiscoveryPolicy)
    minimum_confidence: float = 0.0
    manual_urls: list[str] = field(default_factory=list)
    discovery_providers: list[str] | None = None  # None = every registered provider

    def as_dict(self) -> dict:
        """JSON-safe shape — persisted verbatim as `discovery_runs.request_json`,
        so a run's exact parameters are always reproducible later.
        """
        return {
            "country": self.country, "region": self.region, "city": self.city,
            "postal_area": self.postal_area, "language": self.language,
            "rental_categories": self.rental_categories, "property_types": self.property_types,
            "room_or_shared_housing_intent": self.room_or_shared_housing_intent,
            "long_or_short_term": self.long_or_short_term, "student_housing": self.student_housing,
            "professional_housing": self.professional_housing, "commercial_rental": self.commercial_rental,
            "max_candidates": self.max_candidates, "allowed_domains": self.allowed_domains,
            "excluded_domains": self.excluded_domains,
            "refresh_policy": {"max_age_days": self.refresh_policy.max_age_days, "force_refresh": self.refresh_policy.force_refresh},
            "minimum_confidence": self.minimum_confidence, "manual_urls": self.manual_urls,
            "discovery_providers": self.discovery_providers,
        }


@dataclass
class DiscoveredURL:
    """One raw hit from a `DiscoveryProvider`, before normalization/dedup/evidence
    collection — the provider's entire contract is "hand back whatever URLs you
    found," nothing more.
    """

    url: str
    name: str | None = None
    source_hint: str | None = None  # e.g. the search phrase or seed category that produced this hit
    metadata: dict = field(default_factory=dict)


@dataclass
class PlatformEvidence:
    """One piece of evidence collected about one candidate — "Never overwrite
    evidence" (the mission's own words): this is an append-only fact, never
    revised in place.
    """

    candidate_id: str
    evidence_type: str
    discovery_provider: str
    value: dict
    collected_at: datetime
    confidence: float | None = None
    run_id: str | None = None
    id: int | None = None


@dataclass
class PlatformVerificationResult:
    """One verification check's outcome — "Verification failures must not erase a
    platform" (the mission's own words): a failed check is recorded honestly,
    never removes the candidate.
    """

    candidate_id: str
    check_type: str
    result: str  # "pass" | "fail" | "unknown"
    observed_at: datetime
    detail: dict | None = None
    run_id: str | None = None
    id: int | None = None


@dataclass
class PlatformCapabilityEstimate:
    """One estimated capability — always `is_estimate=True` here; nothing in this
    sprint confirms a capability via a real connector (see docs/29 "Capability
    Estimation").
    """

    candidate_id: str
    capability_key: str
    estimated_value: dict
    observed_at: datetime
    is_estimate: bool = True
    run_id: str | None = None
    id: int | None = None


@dataclass
class PlatformCandidate:
    """One discovered platform candidate's current state — mutable, like
    `storage.models.Platform` itself, since classification/status/confidence
    genuinely change as more evidence arrives. Never the canonical registry;
    promotion to a real `platforms` row only ever happens through the existing
    `DiscoveryAgent.sync_platforms()` path (see docs/29 "Registry Integration").
    """

    candidate_id: str
    normalized_domain: str
    name: str
    raw_url: str
    status: PlatformStatus
    classification: PlatformClassification
    first_discovered_at: datetime
    last_seen_at: datetime
    last_run_id: str
    country: str | None = None
    region: str | None = None
    city: str | None = None
    confidence: float | None = None
    matched_platform_id: str | None = None
    id: int | None = None


@dataclass
class PlatformEvaluation:
    """The complete evaluated picture for one candidate, produced by the pipeline
    before storing — evidence, verification, capability estimates, and the
    resulting classification/status/confidence all in one place, with a plain-
    language explanation of how the pipeline got there.
    """

    candidate: PlatformCandidate
    evidence: list[PlatformEvidence] = field(default_factory=list)
    verification: list[PlatformVerificationResult] = field(default_factory=list)
    capabilities: list[PlatformCapabilityEstimate] = field(default_factory=list)
    explanation: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiscoveryRun:
    """One `AutomaticDiscoveryAgent.run()` execution — the append-only header row
    every candidate/evidence/verification/capability/observation from this run
    links back to.
    """

    request: DiscoveryRequest
    started_at: datetime
    providers_used: list[str] = field(default_factory=list)
    completed_at: datetime | None = None
    total_candidates: int = 0
    new_candidate_count: int = 0
    duplicate_count: int = 0
    verified_count: int = 0
    supported_count: int = 0
    unsupported_count: int = 0
    notes: str | None = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    id: int | None = None


@dataclass
class PlatformDiscoveryResult:
    """The top-level return value of `AutomaticDiscoveryAgent.run()` — "Return
    supported and unsupported platforms separately" (the mission's own words).
    """

    run: DiscoveryRun
    supported: list[PlatformCandidate] = field(default_factory=list)
    unsupported: list[PlatformCandidate] = field(default_factory=list)
    needs_review: list[PlatformCandidate] = field(default_factory=list)
    duplicates: list[PlatformCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiscoveryStatistics:
    """Aggregate figures across every discovery run so far — mirrors
    `FeedbackStatistics`/`RankingStatistics`'s own "computed from completed
    results, never inside the engine itself" separation.
    """

    total_runs: int
    total_candidates: int
    candidates_by_status: dict[str, int] = field(default_factory=dict)
    candidates_by_classification: dict[str, int] = field(default_factory=dict)
    average_confidence: float | None = None
    provider_candidate_counts: dict[str, int] = field(default_factory=dict)
    duplicate_rate: float | None = None
    verification_pass_rate: float | None = None
    candidate_to_supported_rate: float | None = None

    def as_dict(self) -> dict:
        return {
            "total_runs": self.total_runs, "total_candidates": self.total_candidates,
            "candidates_by_status": self.candidates_by_status,
            "candidates_by_classification": self.candidates_by_classification,
            "average_confidence": self.average_confidence,
            "provider_candidate_counts": self.provider_candidate_counts,
            "duplicate_rate": self.duplicate_rate, "verification_pass_rate": self.verification_pass_rate,
            "candidate_to_supported_rate": self.candidate_to_supported_rate,
        }


@dataclass
class DiscoveryComparison:
    """Comparing two discovery runs — mirrors `search_memory.models.SearchComparison`'s
    own shape, applied to platform discovery instead of apartment listings.
    """

    previous_run_id: str
    current_run_id: str
    new_candidate_ids: list[str] = field(default_factory=list)
    removed_or_unreachable_candidate_ids: list[str] = field(default_factory=list)
    changed_metadata_candidate_ids: list[str] = field(default_factory=list)
    changed_verification_status_candidate_ids: list[str] = field(default_factory=list)
    changed_connector_availability_candidate_ids: list[str] = field(default_factory=list)
    newly_supported_locations: list[str] = field(default_factory=list)
    newly_supported_rental_categories: list[str] = field(default_factory=list)
