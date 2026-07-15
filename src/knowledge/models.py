"""Domain-level knowledge shapes — read-side views over accumulated observations
(`platform_performance_observations`, `apartments`, `search_requests`). See
docs/16_Knowledge_Engine.md for the underlying metric definitions. Every field here is
either a stored rollup or a plain average/count/ratio computed at read time — nothing
predicted, scored by a model, or decided automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PlatformKnowledge:
    """Everything accumulated about one platform — "PlatformReliability(platform)" /
    one entry of "PlatformStatistics()" from the v2.0 Step 4 mission. `reliability_score`/
    `success_rate`/`avg_response_time_ms`/`avg_apartment_count`/`duplicate_rate` are the
    stored Platform Intelligence rollup columns (docs/05_Platform_Discovery.md);
    `avg_image_quality`/`availability_coverage`/`avg_ranking_score` are computed at read
    time from the platform's recent observations (no rollup column exists for them —
    adding one would be schema invention beyond what migration 0001 already designed);
    `avg_price` is computed from the platform's currently-known apartments.

    `avg_image_quality` reports "Average Images" from the mission using the already
    -designed `image_quality_score` metric (fraction of listings with at least one
    image) rather than a raw mean image count — a genuine average-count metric would
    need a new observation column, which this step deliberately doesn't add.
    """

    platform_id: str
    platform_name: str
    observation_count: int
    reliability_score: float | None
    success_rate: float | None
    failure_rate: float | None
    avg_response_time_ms: float | None
    duplicate_rate: float | None
    avg_image_quality: float | None
    avg_apartment_count: float | None
    availability_coverage: float | None
    avg_price: float | None
    avg_ranking_score: float | None
    last_successful_search_at: datetime | None
    last_failed_search_at: datetime | None


@dataclass
class ConnectorHealth:
    """"ConnectorHealth()" from the mission — one entry per platform's connector (this
    project has exactly one connector per platform, so this is presently a re-grouping
    of the same observations `PlatformKnowledge` uses, not a separate data source).
    `avg_response_time_ms` doubles as "Runtime" and, until the Connector SDK (v2.0
    Step 5, not yet built) can time fetch and parse separately, the best available
    proxy for "Average Parsing Time" too — documented here rather than silently
    assumed, since it's currently fetch+parse combined.
    """

    platform_id: str
    connector_name: str | None
    connector_version: str | None
    observation_count: int
    success_count: int
    failure_count: int
    avg_response_time_ms: float | None
    avg_image_quality: float | None
    avg_listing_count: float | None


@dataclass
class CityKnowledge:
    """"CityStatistics()" / "AverageCityPrice(city)" from the mission. `location` is
    the same free-text string Search Memory already keys on
    (docs/17_Search_Memory.md) — there is no separate country/region breakdown
    anywhere in this schema (`SearchRequest.location` is a single unstructured string,
    and no geocoding exists yet — that's the Deep Analysis Engine, v2.0 Step 7).

    "Most common property types" from the mission is not tracked here: no
    per-apartment property/rental-type field exists anywhere in the schema (V1.0
    confirmed residential apartments as the only rental type in scope — see
    docs/00_Project_Vision.md), so there is currently exactly one type system-wide.
    Tracking it meaningfully would require adding new `Apartment` schema first, which
    is out of this step's scope ("only accumulate evidence," not invent new facts to
    accumulate).
    """

    location: str
    search_count: int
    avg_apartment_count: float | None
    avg_price: float | None
    avg_availability_ratio: float | None
    most_reliable_platform_ids: list[str] = field(default_factory=list)


@dataclass
class KnowledgeSummary:
    """"KnowledgeSummary()" from the mission — a single top-level snapshot combining
    Platform Intelligence with the search-level statistics Search Memory (v2.0 Step 3)
    already computes; not a reimplementation of `search_memory_service.search_statistics()`.
    """

    generated_at: datetime
    total_observations: int
    platforms: list[PlatformKnowledge]
    average_search_execution_time_ms: float | None
    average_search_apartment_count: float | None
