"""Walking distance from the apartment to its city's reference center point.

Real math (haversine — `src.analysis.geo`), not a live routing API: given the
apartment's coordinates and a curated reference point, the straight-line distance is
exact arithmetic. Two pieces of evidence are both required, and both are honestly
absent today: `Apartment.latitude`/`.longitude` (no connector populates them yet — see
docs/03_Data_Model.md) and a curated `knowledge_entries` "city_center" reference point
for the apartment's location (nothing seeds this automatically). This analyzer is
correct and tested against real coordinates now, dormant in the live pipeline until
either piece of evidence exists for real.
"""

from __future__ import annotations

import json

from src.analysis.base_analyzer import BaseAnalyzer
from src.analysis.geo import haversine_km
from src.analysis.models import AnalysisContext, AnalyzerMetadata, AnalyzerResult
from src.analysis.registry import register_analyzer
from src.storage import reference_data_repository
from src.storage.models import Apartment

_VERSION = "1.0.0"

# Straight-line distance at or beyond this many km scores the minimum 0.0 — a simple,
# documented, tunable constant (walking ~30-40 minutes), not a hidden magic number.
_MAX_SCORED_DISTANCE_KM = 5.0


@register_analyzer
class WalkingDistanceAnalyzer(BaseAnalyzer):
    analyzer_name = "walking_distance"

    def metadata(self) -> AnalyzerMetadata:
        return AnalyzerMetadata(
            analyzer_name=self.analyzer_name,
            version=_VERSION,
            category="proximity",
            description="Straight-line distance from the apartment to its city's reference center point.",
            required_evidence=["apartment.latitude/longitude", "knowledge_entries: city_center/<location>"],
        )

    def analyze(self, apartment: Apartment, context: AnalysisContext) -> AnalyzerResult:
        if apartment.latitude is None or apartment.longitude is None:
            return self._no_evidence(apartment, context, "Apartment has no coordinates")

        entry = reference_data_repository.get_knowledge_entry(context.conn, "city_center", context.location)
        if entry is None:
            return self._no_evidence(apartment, context, f"No city center reference point for {context.location!r}")

        center = json.loads(entry.value_json)
        distance_km = haversine_km(apartment.latitude, apartment.longitude, center["latitude"], center["longitude"])
        score = max(0.0, min(1.0, 1 - distance_km / _MAX_SCORED_DISTANCE_KM))

        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            apartment_id=apartment.id,
            score=score,
            confidence=1.0,
            evidence=[f"{distance_km:.2f} km from {context.location} center"],
            warnings=[],
            computed_at=context.computed_at,
            version=_VERSION,
            source="haversine_calculation",
        )

    def _no_evidence(self, apartment: Apartment, context: AnalysisContext, reason: str) -> AnalyzerResult:
        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            apartment_id=apartment.id,
            score=None,
            confidence=None,
            evidence=[],
            warnings=[reason],
            computed_at=context.computed_at,
            version=_VERSION,
            source="haversine_calculation",
        )
