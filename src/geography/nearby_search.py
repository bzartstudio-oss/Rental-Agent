"""`NearbySearch` — finds known places of a given category near a coordinate, via
whichever `GeoProvider` is available, with the same optional caching
`DistanceCalculator` uses. See docs/26_Geographic_Intelligence.md "Nearby Search".
"""

from __future__ import annotations

from src.geography.base_provider import GeoContext
from src.geography.cache import GeoCache
from src.geography.factory import GeoProviderFactory
from src.geography.models import Coordinates, NearbyPlace

# The 17 categories the mission names — a plain tuple of strings, not an enum, so a
# future category never requires a code change here, only a provider that
# recognizes it (the same "open-ended by convention" shape
# `ConnectorMetadata.extra_capabilities` already uses for the same reason).
NEARBY_CATEGORIES: tuple[str, ...] = (
    "supermarket", "pharmacy", "hospital", "clinic", "university", "school", "park",
    "restaurant", "gym", "bank", "atm", "parking", "bus_stop", "metro_station",
    "train_station", "coworking_space", "shopping_center",
)


class NearbySearch:
    def __init__(self, cache: GeoCache | None = None, provider_id: str | None = None) -> None:
        self._cache = cache
        self._provider_id = provider_id

    def find_nearby(
        self,
        origin: Coordinates,
        category: str,
        context: GeoContext | None = None,
    ) -> list[NearbyPlace]:
        context = context or GeoContext()
        provider = (
            GeoProviderFactory.get(self._provider_id)
            if self._provider_id is not None
            else GeoProviderFactory.get_best_available()
        )

        cache_key = GeoCache.make_key("nearby", provider.provider_id, origin, category, context.location)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        results = provider.find_nearby(origin, category, context)

        if self._cache is not None:
            self._cache.set(cache_key, results)
        return results

    def find_nearby_all_categories(
        self,
        origin: Coordinates,
        context: GeoContext | None = None,
    ) -> dict[str, list[NearbyPlace]]:
        return {category: self.find_nearby(origin, category, context) for category in NEARBY_CATEGORIES}
