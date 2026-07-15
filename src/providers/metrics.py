"""`ProviderMetrics` — one provider run's metrics, per the mission's list (execution
time, success/failure, listing count, duplicate count, parsing quality, image
availability, availability coverage, response statistics). See
docs/24_Production_Providers.md "Metrics".

Every formula is reused from `src.knowledge.metrics` (v2.0 Step 4) — this module
computes nothing new, it only shapes the *same* numbers into a provider-scoped
dataclass and, via `record_provider_metrics()`, into a real
`platform_performance_observations` row (the Knowledge Engine already does this for
every connector's run; this makes the same call explicitly for a provider's run
rather than relying on `core/agent.py`'s own bookkeeping to get there indirectly).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from src.connectors.sdk.result import ConnectorResult
from src.knowledge import knowledge_service
from src.knowledge import metrics as knowledge_metrics


@dataclass
class ProviderMetrics:
    """`duplicate_rate` (a fraction, not a raw count) matches the mission's "duplicate
    count" ask — this project's Knowledge Engine has only ever tracked duplication as
    a rate (`platform_performance_observations.duplicate_rate`, migration 0001), not a
    raw count column; introducing a second, differently-shaped duplicate signal here
    would be new schema this sprint doesn't call for. "Response statistics" (the
    mission's phrase) is `execution_time_ms` for one run — the *aggregate* view across
    many runs (average/min/max) is `ProviderStatistics`' job, not this dataclass's.
    """

    provider_id: str
    platform_id: str
    execution_time_ms: int | None
    success: bool
    listing_count: int
    duplicate_rate: float | None
    extraction_quality_score: float | None
    image_quality_score: float | None
    availability_quality_score: float | None
    error: str | None = None


def build_provider_metrics(provider_id: str, platform_id: str, result: ConnectorResult) -> ProviderMetrics:
    listings = result.listings
    return ProviderMetrics(
        provider_id=provider_id,
        platform_id=platform_id,
        execution_time_ms=result.response_time_ms,
        success=result.success,
        listing_count=len(listings),
        duplicate_rate=knowledge_metrics.duplicate_rate(listings) if listings else None,
        extraction_quality_score=knowledge_metrics.extraction_quality_score(listings) if listings else None,
        image_quality_score=knowledge_metrics.image_quality_score(listings) if listings else None,
        availability_quality_score=knowledge_metrics.availability_quality_score(listings) if listings else None,
        error=result.error,
    )


def record_provider_metrics(
    conn: sqlite3.Connection,
    metrics: ProviderMetrics,
    result: ConnectorResult,
    search_id: str,
    observed_at: datetime,
) -> None:
    """Writes `metrics` into `platform_performance_observations` via the exact same
    `knowledge_service.record_platform_observation()` every connector's run already
    goes through — "Store observations inside the Knowledge Engine" (the mission's
    words) is satisfied by reusing that one write path, not adding a second one.

    `record_platform_observation()` recomputes extraction/image/availability/
    duplicate scores itself from `raw_listings` (the same `knowledge_metrics`
    functions `build_provider_metrics()` already called) — passing `result.listings`
    through here means that recomputation lands on identical numbers, not a second,
    differently-derived set. This is one formula invoked from two call sites (an
    immediate, inspectable `ProviderMetrics` and a persisted observation row), not the
    formula duplicated.
    """
    knowledge_service.record_platform_observation(
        conn,
        metrics.platform_id,
        search_id,
        results_count=metrics.listing_count,
        failed=not metrics.success,
        response_time_ms=metrics.execution_time_ms,
        raw_listings=result.listings or None,
        ranking_usefulness_score=None,
        parsing_success=metrics.success,
        observed_at=observed_at,
    )
