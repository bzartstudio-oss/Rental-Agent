"""Shared logic for every "nearby X" analyzer (supermarkets, pharmacies, hospitals,
universities, schools, parks, restaurants, gyms, parking) — nine analyzers, all
structurally identical: count known points of interest of one category near an
apartment's location, from curated reference data, normalize to a 0-1 score.

Evidence source: `storage.reference_data_repository` (`knowledge_entries`, category
`"nearby_amenities"`, key `f"{location}:{amenity_type}"`, `value_json =
{"count": <int>}`) — curated facts a human enters, not a live places/maps API (no such
vendor decision has been made, see docs/07_Analysis_Engine.md "Open Questions" and
docs/19_Analysis_Engine.md). No apartment ever has this data seeded automatically;
every one of these analyzers honestly reports "no evidence" until a real fact is
curated for that location, exactly like every other dormant-until-real-data field in
this project (`platforms.connector_version`, `compare_coordinates`, etc.).
"""

from __future__ import annotations

import json

from src.analysis.base_analyzer import BaseAnalyzer
from src.analysis.models import AnalysisContext, AnalyzerMetadata, AnalyzerResult
from src.analysis.registry import register_analyzer
from src.storage import reference_data_repository
from src.storage.models import Apartment

_VERSION = "1.0.0"
_KNOWLEDGE_CATEGORY = "nearby_amenities"

# A count at or above this many known amenities scores the maximum 1.0 — a simple,
# documented, tunable constant, not a hidden magic number buried in the formula.
_SATURATION_COUNT = 5


class NearbyAmenityAnalyzer(BaseAnalyzer):
    """Subclasses set `analyzer_name`, `amenity_type` (the curated data's key), and
    `display_name` (for descriptions/reports) — nothing else. All nine "nearby X"
    analyzers below are this shared class with three lines of configuration each.
    """

    amenity_type: str
    display_name: str

    def metadata(self) -> AnalyzerMetadata:
        return AnalyzerMetadata(
            analyzer_name=self.analyzer_name,
            version=_VERSION,
            category="amenity",
            description=f"Counts known {self.display_name.lower()} near the apartment's location.",
            required_evidence=[f"knowledge_entries: {_KNOWLEDGE_CATEGORY}/<location>:{self.amenity_type}"],
        )

    def analyze(self, apartment: Apartment, context: AnalysisContext) -> AnalyzerResult:
        key = f"{context.location}:{self.amenity_type}"
        entry = reference_data_repository.get_knowledge_entry(context.conn, _KNOWLEDGE_CATEGORY, key)

        if entry is None:
            return AnalyzerResult(
                analyzer_name=self.analyzer_name,
                apartment_id=apartment.id,
                score=None,
                confidence=None,
                evidence=[],
                warnings=[f"No curated {self.amenity_type} data for {context.location!r} yet"],
                computed_at=context.computed_at,
                version=_VERSION,
                source="knowledge_entries",
            )

        count = json.loads(entry.value_json).get("count", 0)
        score = min(count / _SATURATION_COUNT, 1.0)
        return AnalyzerResult(
            analyzer_name=self.analyzer_name,
            apartment_id=apartment.id,
            score=score,
            confidence=0.8,
            evidence=[f"{count} known {self.amenity_type}(s) near {context.location}"],
            warnings=[],
            computed_at=context.computed_at,
            version=_VERSION,
            source="knowledge_entries",
        )


@register_analyzer
class NearbySupermarketsAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_supermarkets"
    amenity_type = "supermarket"
    display_name = "Nearby Supermarkets"


@register_analyzer
class NearbyPharmaciesAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_pharmacies"
    amenity_type = "pharmacy"
    display_name = "Nearby Pharmacies"


@register_analyzer
class NearbyHospitalsAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_hospitals"
    amenity_type = "hospital"
    display_name = "Nearby Hospitals"


@register_analyzer
class NearbyUniversitiesAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_universities"
    amenity_type = "university"
    display_name = "Nearby Universities"


@register_analyzer
class NearbySchoolsAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_schools"
    amenity_type = "school"
    display_name = "Nearby Schools"


@register_analyzer
class NearbyParksAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_parks"
    amenity_type = "park"
    display_name = "Nearby Parks"


@register_analyzer
class NearbyRestaurantsAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_restaurants"
    amenity_type = "restaurant"
    display_name = "Nearby Restaurants"


@register_analyzer
class NearbyGymsAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_gyms"
    amenity_type = "gym"
    display_name = "Nearby Gyms"


@register_analyzer
class NearbyParkingAnalyzer(NearbyAmenityAnalyzer):
    analyzer_name = "nearby_parking"
    amenity_type = "parking"
    display_name = "Nearby Parking"
