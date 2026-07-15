"""`HaversineGeoProvider` — the one built-in, real, working `GeoProvider`. See
docs/26_Geographic_Intelligence.md "Providers".

**What's real**: straight-line distance is exact arithmetic (`src.analysis.geo.
haversine_km`, reused, not reimplemented — the same great-circle math
`walking_distance`/`public_transport` analyzers already use). Nearby-search counts
are real, curated facts from `knowledge_entries` (the same `"nearby_amenities"`
category/key convention `analysis/analyzers/nearby_amenity.py` already established —
curated data entered for those analyzers is immediately usable here too, for the
same 9 categories, plus 8 new ones this sprint adds).

**What's honestly estimated, not real routing**: walking/cycling/driving/public-
transport travel time. No live routing API is integrated (a deliberately deferred
vendor decision, same as the Analysis Engine's own "no geocoding/places/transit API"
— see docs/19_Analysis_Engine.md "Deliberately Not Built"). Travel time here is
straight-line distance divided by a documented, tunable average speed per mode — a
real, transparent estimate that ignores actual roads/terrain/traffic, never
presented as equivalent to a real route. Confidence is scored lower for these
estimates than for the exact distance calculation itself, reflecting that honestly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.analysis.geo import haversine_km
from src.geography.base_provider import GeoContext, GeoProvider
from src.geography.exceptions import GeoCalculationError
from src.geography.metadata import GeoProviderMetadata
from src.geography.models import Coordinates, GeoResult, NearbyPlace, TravelMode
from src.geography.nearby_search import NEARBY_CATEGORIES
from src.geography.registry import register_geo_provider
from src.storage import reference_data_repository
from src.utils.logging import get_logger

logger = get_logger(__name__)

_VERSION = "1.0.0"
_KNOWLEDGE_CATEGORY = "nearby_amenities"  # same category analysis/analyzers/nearby_amenity.py uses

# Average speeds in km/h — documented, tunable constants, not hidden magic numbers.
# Each is a real-world rough average, not a fabricated number: walking ~5 km/h,
# cycling ~15 km/h, urban driving ~30 km/h (accounting for traffic/stops/lights),
# public transport ~20 km/h (accounting for stops and waiting).
_AVERAGE_SPEED_KMH: dict[TravelMode, float] = {
    TravelMode.WALKING: 5.0,
    TravelMode.CYCLING: 15.0,
    TravelMode.DRIVING: 30.0,
    TravelMode.PUBLIC_TRANSPORT: 20.0,
}

# The exact haversine calculation is deterministic, real arithmetic — full
# confidence. An estimated travel time (straight-line distance ÷ an assumed average
# speed, ignoring real roads/terrain/traffic) is honestly much less certain.
_STRAIGHT_LINE_CONFIDENCE = 1.0
_ESTIMATED_TRAVEL_TIME_CONFIDENCE = 0.4
_CURATED_NEARBY_CONFIDENCE = 0.8  # matches nearby_amenity.py's own confidence for the same evidence


class HaversineGeoProvider(GeoProvider):
    provider_id = "haversine"

    def is_available(self) -> bool:
        """Always available — pure math and (optionally) a database read, no
        external service, no credential, no network dependency.
        """
        return True

    def metadata(self) -> GeoProviderMetadata:
        return GeoProviderMetadata(
            provider_id=self.provider_id,
            display_name="Haversine (straight-line + estimated travel time)",
            supports_real_routing=False,
            supported_modes=[mode.value for mode in TravelMode],
            supported_nearby_categories=list(NEARBY_CATEGORIES),
            description=(
                "Real great-circle distance via the haversine formula; travel time for "
                "walking/cycling/driving/public transport is a documented estimate "
                "(distance ÷ assumed average speed), not real routing. Nearby-search "
                "results are curated counts from knowledge_entries, not a live places API."
            ),
        )

    def calculate_distance(
        self,
        origin: Coordinates,
        destination: Coordinates,
        mode: TravelMode,
        context: GeoContext,
    ) -> GeoResult:
        try:
            distance_km = haversine_km(origin[0], origin[1], destination[0], destination[1])
        except (TypeError, ValueError) as exc:
            raise GeoCalculationError(f"haversine: invalid coordinates: {exc}") from exc

        now = datetime.now(timezone.utc)

        if mode is TravelMode.STRAIGHT_LINE:
            return GeoResult(
                origin=origin, destination=destination, mode=mode,
                distance_km=distance_km, travel_time_minutes=None,
                confidence=_STRAIGHT_LINE_CONFIDENCE, computed_at=now,
                provider_id=self.provider_id, calculation_method="haversine",
            )

        speed_kmh = _AVERAGE_SPEED_KMH.get(mode)
        if speed_kmh is None:
            raise GeoCalculationError(f"haversine: unsupported travel mode {mode!r}")

        travel_time_minutes = (distance_km / speed_kmh) * 60
        return GeoResult(
            origin=origin, destination=destination, mode=mode,
            distance_km=distance_km, travel_time_minutes=travel_time_minutes,
            confidence=_ESTIMATED_TRAVEL_TIME_CONFIDENCE, computed_at=now,
            provider_id=self.provider_id,
            calculation_method=f"haversine+estimated_speed({speed_kmh:.0f}km/h)",
        )

    def find_nearby(self, origin: Coordinates, category: str, context: GeoContext) -> list[NearbyPlace]:
        now = datetime.now(timezone.utc)
        if context.conn is None or context.location is None:
            return []

        key = f"{context.location}:{category}"
        entry = reference_data_repository.get_knowledge_entry(context.conn, _KNOWLEDGE_CATEGORY, key)

        if entry is None:
            return [
                NearbyPlace(
                    category=category, count=None, distance_km=None, travel_time_minutes=None,
                    confidence=None, computed_at=now, provider_id=self.provider_id,
                    calculation_method="knowledge_entries",
                    warnings=[f"No curated {category!r} data for {context.location!r} yet"],
                )
            ]

        count = json.loads(entry.value_json).get("count", 0)
        return [
            NearbyPlace(
                category=category, count=count, distance_km=None, travel_time_minutes=None,
                confidence=_CURATED_NEARBY_CONFIDENCE, computed_at=now, provider_id=self.provider_id,
                calculation_method="knowledge_entries",
            )
        ]


register_geo_provider(HaversineGeoProvider())
