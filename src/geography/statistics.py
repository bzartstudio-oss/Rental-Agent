"""`GeoStatistics` — computed *from* a completed `GeographicEngine.enrich_many()`'s
results, never inside `GeographicEngine` itself (single responsibility, the same
separation `filter_engine/statistics.py` keeps from `filter_engine/engine.py`). See
docs/26_Geographic_Intelligence.md "Architecture".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.geography.models import GeoEnrichment


@dataclass
class GeoStatistics:
    total_apartments: int
    enriched_count: int  # apartments with at least one distance or nearby result
    coverage_rate: float | None  # enriched_count / total_apartments
    average_confidence_by_mode: dict[str, float] = field(default_factory=dict)
    nearby_coverage_by_category: dict[str, float] = field(default_factory=dict)  # fraction with count evidence

    def as_dict(self) -> dict:
        """JSON-safe shape for `geo_enrichment_history.summary_json` — a plain dict,
        not a bespoke serializer, since every field here is already JSON-native.
        """
        return {
            "total_apartments": self.total_apartments,
            "enriched_count": self.enriched_count,
            "coverage_rate": self.coverage_rate,
            "average_confidence_by_mode": self.average_confidence_by_mode,
            "nearby_coverage_by_category": self.nearby_coverage_by_category,
        }


def compute_geo_statistics(enrichments: dict[str, GeoEnrichment]) -> GeoStatistics:
    total = len(enrichments)
    enriched = sum(1 for e in enrichments.values() if e.distances or any(e.nearby.values()))

    confidence_votes: dict[str, list[float]] = {}
    for enrichment in enrichments.values():
        for mode, result in enrichment.distances.items():
            confidence_votes.setdefault(mode.value, []).append(result.confidence)

    nearby_votes: dict[str, list[bool]] = {}
    for enrichment in enrichments.values():
        for category, places in enrichment.nearby.items():
            has_evidence = any(place.count is not None for place in places)
            nearby_votes.setdefault(category, []).append(has_evidence)

    return GeoStatistics(
        total_apartments=total,
        enriched_count=enriched,
        coverage_rate=(enriched / total) if total else None,
        average_confidence_by_mode={
            mode: sum(votes) / len(votes) for mode, votes in confidence_votes.items()
        },
        nearby_coverage_by_category={
            category: sum(votes) / len(votes) for category, votes in nearby_votes.items()
        },
    )
