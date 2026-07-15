"""`GeographicEngine` — the orchestrator: apartment coordinates in, a read-only
`GeoEnrichment` out. See docs/26_Geographic_Intelligence.md "Architecture".

Mirrors `FilterEngine`'s single-responsibility shape: this class does not construct
a connector, does not touch the Analysis/Ranking Engines, and — per the mission's own
words ("It NEVER modifies original apartment data") — never writes back onto the
`Apartment` it was given. Its only job is turning (apartment, context) into a
`GeoEnrichment`, an independent artifact handed to the report generator the same way
`analysis_results`/`ai_summary` already are (see docs/26 "Future Extensions" for why
this, not wiring straight into Analysis Engine's own scoring, is the deliberate
integration point for this sprint).

The reference point an apartment's distances are measured *to* reuses the exact
`"city_center"` knowledge_entries convention `analysis/analyzers/walking_distance.py`
already established — not a second, competing convention for the same idea.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.geography.base_provider import GeoContext
from src.geography.cache import GeoCache
from src.geography.calculators import DistanceCalculator
from src.geography.models import GeoEnrichment, TravelMode
from src.geography.nearby_search import NEARBY_CATEGORIES, NearbySearch
from src.storage import reference_data_repository
from src.storage.models import Apartment

_CITY_CENTER_CATEGORY = "city_center"  # same category walking_distance.py already reads


class GeographicEngine:
    def __init__(self, cache: GeoCache | None = None, provider_id: str | None = None) -> None:
        self._cache = cache
        self._distance_calculator = DistanceCalculator(cache=cache, provider_id=provider_id)
        self._nearby_search = NearbySearch(cache=cache, provider_id=provider_id)

    def enrich(self, apartment: Apartment, context: GeoContext | None = None) -> GeoEnrichment:
        """Never raises for missing evidence — an apartment with no coordinates, or a
        location with no curated `city_center` reference point, honestly gets an empty
        `GeoEnrichment` (no fabricated distance), exactly like `walking_distance.py`'s
        own "no evidence" path for the same two facts.
        """
        context = context or GeoContext()
        enrichment = GeoEnrichment(apartment_id=apartment.id, computed_at=datetime.now(timezone.utc))

        if apartment.latitude is None or apartment.longitude is None:
            return enrichment
        origin = (apartment.latitude, apartment.longitude)

        destination = self._resolve_reference_point(context)
        if destination is not None:
            for mode in TravelMode:
                enrichment.distances[mode] = self._distance_calculator.calculate(origin, destination, mode, context)

        enrichment.nearby = self._nearby_search.find_nearby_all_categories(origin, context)
        return enrichment

    def enrich_many(
        self,
        apartments: list[Apartment],
        context: GeoContext | None = None,
    ) -> dict[str, GeoEnrichment]:
        """The common case: every apartment in a search result set, keyed by id —
        what `core/agent.py`/`report_generator.py` actually need.
        """
        return {apartment.id: self.enrich(apartment, context) for apartment in apartments}

    def _resolve_reference_point(self, context: GeoContext) -> tuple[float, float] | None:
        if context.conn is None or context.location is None:
            return None
        entry = reference_data_repository.get_knowledge_entry(context.conn, _CITY_CENTER_CATEGORY, context.location)
        if entry is None:
            return None
        center = json.loads(entry.value_json)
        return (center["latitude"], center["longitude"])


__all__ = ["GeographicEngine", "NEARBY_CATEGORIES"]
