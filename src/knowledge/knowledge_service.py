"""The Knowledge Engine's write- and read-side orchestration (v2.0 Step 4 mission).
Functions, not a class — same reasoning as history_service.py/search_memory_service.py:
no state beyond the `conn` every call already takes.

Write side: `record_platform_observation` is called once per platform a search
attempted (success or failure) — see core/agent.py's integration, which calls it after
`search_memory_service.record_completed_search()` (per the mission's explicit
Apartment History -> Search Memory -> Knowledge Engine ordering). Every call appends
one `platform_performance_observations` row (never overwritten) and recomputes that
platform's rollup columns on `platforms` over a recent window.

Read side: `best_platforms`/`platform_reliability`/`connector_health`/
`average_city_price`/`knowledge_summary`/`platform_statistics`/`city_statistics` — the
mission's PUBLIC METHODS, translated to this project's snake_case convention. Every one
is a plain average, count, or ratio over already-stored data — no prediction, no
scoring model, no automatic decision-making anywhere in this module.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from statistics import mean

from src.connectors.base import RawListing
from src.discovery import platform_registry
from src.knowledge import metrics
from src.knowledge.models import CityKnowledge, ConnectorHealth, KnowledgeSummary, PlatformKnowledge
from src.search_memory import search_memory_service
from src.storage import platform_intelligence_repository, search_memory_repository
from src.storage.models import Platform, PlatformPerformanceObservation

_RECENT_WINDOW = 20


def record_platform_observation(
    conn: sqlite3.Connection,
    platform_id: str,
    search_id: str,
    *,
    results_count: int,
    failed: bool,
    response_time_ms: int | None,
    raw_listings: list[RawListing] | None,
    ranking_usefulness_score: float | None,
    parsing_success: bool,
    observed_at: datetime,
) -> None:
    """"Learning From Failure" (docs/16_Knowledge_Engine.md): even a platform whose
    connector raised gets a row here — `raw_listings=None` (or empty) correctly
    produces `None` quality scores rather than the observation being skipped entirely.
    """
    observation = PlatformPerformanceObservation(
        platform_id=platform_id,
        search_id=search_id,
        results_count=results_count,
        failed=failed,
        parsing_success=parsing_success,
        observed_at=observed_at,
        response_time_ms=response_time_ms,
        extraction_quality_score=metrics.extraction_quality_score(raw_listings) if raw_listings else None,
        image_quality_score=metrics.image_quality_score(raw_listings) if raw_listings else None,
        availability_quality_score=metrics.availability_quality_score(raw_listings) if raw_listings else None,
        duplicate_rate=metrics.duplicate_rate(raw_listings) if raw_listings else None,
        ranking_usefulness_score=ranking_usefulness_score,
    )
    platform_intelligence_repository.add_observation(conn, observation)
    _recompute_platform_rollups(conn, platform_id)


def _recompute_platform_rollups(conn: sqlite3.Connection, platform_id: str) -> None:
    recent = platform_intelligence_repository.get_recent_observations(conn, platform_id, limit=_RECENT_WINDOW)
    if not recent:
        return

    success_rate = sum(1 for obs in recent if not obs.failed) / len(recent)
    reliability_score = _average(
        [
            _attr_average(recent, "extraction_quality_score"),
            _attr_average(recent, "image_quality_score"),
            _attr_average(recent, "availability_quality_score"),
            _invert(_attr_average(recent, "duplicate_rate")),
        ]
    )

    platform_registry.update_platform_rollups(
        conn,
        platform_id,
        reliability_score=reliability_score,
        success_rate=success_rate,
        avg_response_time_ms=_attr_average(recent, "response_time_ms"),
        avg_apartment_count=mean(obs.results_count for obs in recent),
        duplicate_percentage=_attr_average(recent, "duplicate_rate"),
    )


def platform_reliability(conn: sqlite3.Connection, platform_id: str) -> PlatformKnowledge:
    platform = platform_registry.get_platform(conn, platform_id)
    if platform is None:
        raise KeyError(f"Unknown platform {platform_id!r}")
    return _build_platform_knowledge(conn, platform)


def platform_statistics(conn: sqlite3.Connection, platform_id: str | None = None) -> list[PlatformKnowledge]:
    if platform_id is not None:
        return [platform_reliability(conn, platform_id)]
    return [_build_platform_knowledge(conn, platform) for platform in platform_registry.list_all_platforms(conn)]


def best_platforms(conn: sqlite3.Connection, location: str | None = None, limit: int = 5) -> list[PlatformKnowledge]:
    """Ranked by `reliability_score` descending (platforms with no rollup yet — zero
    observed searches — sort last, not first, since `None` must never be treated as
    "confirmed 0% reliable" or "confirmed best," see docs/03_Data_Model.md).
    """
    if location is None:
        candidates = platform_statistics(conn)
    else:
        candidates = [platform_reliability(conn, pid) for pid in _searched_platform_ids_for_location(conn, location)]

    ranked = sorted(candidates, key=lambda knowledge: (knowledge.reliability_score is None, -(knowledge.reliability_score or 0)))
    return ranked[:limit]


def connector_health(conn: sqlite3.Connection) -> list[ConnectorHealth]:
    results = []
    for platform in platform_registry.list_all_platforms(conn):
        observations = platform_intelligence_repository.get_recent_observations(conn, platform.id, limit=_RECENT_WINDOW)
        if not observations:
            continue
        results.append(
            ConnectorHealth(
                platform_id=platform.id,
                connector_name=platform.connector_name,
                connector_version=platform.connector_version,
                observation_count=len(observations),
                success_count=sum(1 for obs in observations if not obs.failed),
                failure_count=sum(1 for obs in observations if obs.failed),
                avg_response_time_ms=_attr_average(observations, "response_time_ms"),
                avg_image_quality=_attr_average(observations, "image_quality_score"),
                avg_listing_count=mean(obs.results_count for obs in observations),
            )
        )
    return results


def average_city_price(conn: sqlite3.Connection, location: str) -> float | None:
    return _average_apartment_price(conn, _observed_apartment_ids_for_location(conn, location))


def city_statistics(conn: sqlite3.Connection, location: str) -> CityKnowledge:
    records = search_memory_repository.get_search_history(conn, location=location)
    apartment_ids = _observed_apartment_ids_for_location(conn, location)

    return CityKnowledge(
        location=location,
        search_count=len(records),
        avg_apartment_count=_attr_average(records, "apartment_count"),
        avg_price=_average_apartment_price(conn, apartment_ids),
        avg_availability_ratio=_availability_ratio(conn, apartment_ids),
        most_reliable_platform_ids=[knowledge.platform_id for knowledge in best_platforms(conn, location=location, limit=3)],
    )


def knowledge_summary(conn: sqlite3.Connection) -> KnowledgeSummary:
    search_stats = search_memory_service.search_statistics(conn)
    return KnowledgeSummary(
        generated_at=datetime.now(timezone.utc),
        total_observations=platform_intelligence_repository.count_all_observations(conn),
        platforms=platform_statistics(conn),
        average_search_execution_time_ms=search_stats.average_execution_time_ms,
        average_search_apartment_count=search_stats.average_apartment_count,
    )


def _build_platform_knowledge(conn: sqlite3.Connection, platform: Platform) -> PlatformKnowledge:
    recent = platform_intelligence_repository.get_recent_observations(conn, platform.id, limit=_RECENT_WINDOW)
    return PlatformKnowledge(
        platform_id=platform.id,
        platform_name=platform.name,
        observation_count=len(recent),
        reliability_score=platform.reliability_score,
        success_rate=platform.success_rate,
        failure_rate=None if platform.success_rate is None else 1.0 - platform.success_rate,
        avg_response_time_ms=platform.avg_response_time_ms,
        duplicate_rate=platform.duplicate_percentage,
        avg_image_quality=_attr_average(recent, "image_quality_score"),
        avg_apartment_count=platform.avg_apartment_count,
        availability_coverage=_attr_average(recent, "availability_quality_score"),
        avg_price=_average_apartment_price_for_platform(conn, platform.id),
        avg_ranking_score=_attr_average(recent, "ranking_usefulness_score"),
        last_successful_search_at=platform_intelligence_repository.get_last_observed_at(conn, platform.id, failed=False),
        last_failed_search_at=platform_intelligence_repository.get_last_observed_at(conn, platform.id, failed=True),
    )


def _searched_platform_ids_for_location(conn: sqlite3.Connection, location: str) -> list[str]:
    platform_ids: set[str] = set()
    for record in search_memory_repository.get_search_history(conn, location=location):
        platform_ids.update(record.searched_platform_ids or [])
    return sorted(platform_ids)


def _observed_apartment_ids_for_location(conn: sqlite3.Connection, location: str) -> set[str]:
    apartment_ids: set[str] = set()
    for record in search_memory_repository.get_search_history(conn, location=location):
        apartment_ids.update(search_memory_repository.get_observed_apartment_ids(conn, record.id))
    return apartment_ids


def _average_apartment_price(conn: sqlite3.Connection, apartment_ids: set[str]) -> float | None:
    if not apartment_ids:
        return None
    placeholders = ",".join("?" for _ in apartment_ids)
    row = conn.execute(
        f"SELECT AVG(current_price) AS avg_price FROM apartments WHERE id IN ({placeholders})",
        tuple(apartment_ids),
    ).fetchone()
    return row["avg_price"] if row else None


def _average_apartment_price_for_platform(conn: sqlite3.Connection, platform_id: str) -> float | None:
    row = conn.execute(
        "SELECT AVG(current_price) AS avg_price FROM apartments WHERE platform_id = ?", (platform_id,)
    ).fetchone()
    return row["avg_price"] if row else None


def _availability_ratio(conn: sqlite3.Connection, apartment_ids: set[str]) -> float | None:
    if not apartment_ids:
        return None
    placeholders = ",".join("?" for _ in apartment_ids)
    row = conn.execute(
        f"SELECT COUNT(*) AS total, "
        f"SUM(CASE WHEN current_status = 'available' THEN 1 ELSE 0 END) AS available_count "
        f"FROM apartments WHERE id IN ({placeholders})",
        tuple(apartment_ids),
    ).fetchone()
    if not row or not row["total"]:
        return None
    return row["available_count"] / row["total"]


def _attr_average(items: list, attr: str) -> float | None:
    values = [getattr(item, attr) for item in items if getattr(item, attr) is not None]
    return mean(values) if values else None


def _invert(value: float | None) -> float | None:
    return None if value is None else 1.0 - value


def _average(values: list) -> float | None:
    present = [value for value in values if value is not None]
    return mean(present) if present else None
