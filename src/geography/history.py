"""`GeoHistory` — records what one `GeographicEngine.enrich()` call actually
produced for one apartment (provider, calculation method, confidence, a JSON summary
of distances/nearby results), via `storage/geo_history_repository.py` (migration
0006). See docs/26_Geographic_Intelligence.md "Architecture" — mirrors
`filter_engine/history.py`'s exact observe-then-persist shape.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from src.geography.models import GeoEnrichment
from src.storage import geo_history_repository
from src.storage.models import GeoEnrichmentHistoryEntry


@dataclass
class GeoHistoryEntry:
    apartment_id: str
    provider_id: str
    calculation_method: str
    summary: dict
    confidence: float | None
    recorded_at: datetime
    search_id: str | None = None


def summarize_enrichment(enrichment: GeoEnrichment) -> dict:
    """A JSON-safe digest of one `GeoEnrichment` — distance/travel-time per mode plus
    nearby counts per category, not the full dataclass tree (which includes
    non-JSON-native `datetime`/`Enum` values `json.dumps` can't serialize directly).
    """
    return {
        "distances": {
            mode.value: {
                "distance_km": result.distance_km,
                "travel_time_minutes": result.travel_time_minutes,
                "confidence": result.confidence,
            }
            for mode, result in enrichment.distances.items()
        },
        "nearby": {
            category: [{"count": place.count, "confidence": place.confidence} for place in places]
            for category, places in enrichment.nearby.items()
        },
    }


def record_geo_enrichment(
    conn: sqlite3.Connection,
    enrichment: GeoEnrichment,
    recorded_at: datetime,
    search_id: str | None = None,
) -> None:
    """`provider_id`/`calculation_method` are read from the `GeoEnrichment`'s own
    results, never passed in as a literal — this module never needs to know which
    `GeoProvider` actually ran, keeping the engine's provider-independence guarantee
    intact all the way to the history table. `calculation_method` genuinely varies
    per travel mode (e.g. exact `"haversine"` for straight-line vs.
    `"haversine+estimated_speed(...)"` for walking), so distinct methods are recorded
    as `"mixed"` here — the per-mode detail is never lost, it's in `summary_json`.
    """
    confidences = [result.confidence for result in enrichment.distances.values()]
    overall_confidence = (sum(confidences) / len(confidences)) if confidences else None

    provider_ids = {result.provider_id for result in enrichment.distances.values()}
    provider_id = provider_ids.pop() if len(provider_ids) == 1 else ("mixed" if provider_ids else "unknown")

    methods = {result.calculation_method for result in enrichment.distances.values()}
    calculation_method = methods.pop() if len(methods) == 1 else ("mixed" if methods else "unknown")

    geo_history_repository.add_execution(
        conn,
        GeoEnrichmentHistoryEntry(
            apartment_id=enrichment.apartment_id,
            search_id=search_id,
            provider_id=provider_id,
            calculation_method=calculation_method,
            summary=summarize_enrichment(enrichment),
            confidence=overall_confidence,
            recorded_at=recorded_at,
        ),
    )


def get_geo_history_for_apartment(conn: sqlite3.Connection, apartment_id: str) -> list[GeoEnrichmentHistoryEntry]:
    return geo_history_repository.get_history_for_apartment(conn, apartment_id)


def get_geo_history_for_search(conn: sqlite3.Connection, search_id: str) -> list[GeoEnrichmentHistoryEntry]:
    return geo_history_repository.get_history_for_search(conn, search_id)
