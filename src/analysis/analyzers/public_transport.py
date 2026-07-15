"""Distance from the apartment to its city's nearest known public transport stop.

Same evidence model as `walking_distance.py`: real haversine math over the apartment's
coordinates and a curated reference point (`knowledge_entries`, category
`"public_transport"`, key = location, `value_json = {"latitude": ..., "longitude": ...,
"stop_name": ...}` — the nearest known stop, curated by a human, not a live transit API).
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

# Distance to the nearest known stop at or beyond this many km scores the minimum 0.0.
_MAX_SCORED_DISTANCE_KM = 2.0


@register_analyzer
class PublicTransportAnalyzer(BaseAnalyzer):
    analyzer_name = "public_transport"

    def metadata(self) -> AnalyzerMetadata:
        return AnalyzerMetadata(
            analyzer_name=self.analyzer_name,
            version=_VERSION,
            category="transport",
            description="Distance from the apartment to its city's nearest known public transport stop.",
            required_evidence=["apartment.latitude/longitude", "knowledge_entries: public_transport/<location>"],
        )

    def analyze(self, apartment: Apartment, context: AnalysisContext) -> AnalyzerResult:
        if apartment.latitude is None or apartment.longitude is None:
            return self._no_evidence(apartment, context, "Apartment has no coordinates")

        entry = reference_data_repository.get_knowledge_entry(context.conn, "public_transport", context.location)
        if entry is None:
            return self._no_evidence(
                apartment, context, f"No public transport reference stop for {context.location!r}"
            )

        stop = json.loads(entry.value_json)
        distance_km = haversine_km(apartment.latitude, apartment.longitude, stop["latitude"], stop["longitude"])
        score = max(0.0, min(1.0, 1 - distance_km / _MAX_SCORED_DISTANCE_KM))
        stop_name = stop.get("stop_name", "nearest known stop")

        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            apartment_id=apartment.id,
            score=score,
            confidence=1.0,
            evidence=[f"{distance_km:.2f} km from {stop_name}"],
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
