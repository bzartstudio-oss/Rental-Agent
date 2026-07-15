"""`GeoProvider` — the plugin contract every geographic data source implements. See
docs/26_Geographic_Intelligence.md "Providers".

Deliberately provider-agnostic: nothing here assumes haversine math, a curated
`knowledge_entries` fact, or any specific vendor API. A future real routing/places
provider (Google Maps, Mapbox, OSM Overpass, ...) implements this same interface —
`GeographicEngine`, `GeoProviderRegistry`, and every calculator require zero changes
when one is added, the same "prepare interfaces for future integrations" guarantee
`ConnectorFactory`/`ProviderFactory`/`FilterFactory` already proved for their own
domains.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.geography.metadata import GeoProviderMetadata
from src.geography.models import Coordinates, GeoResult, NearbyPlace, TravelMode


@dataclass
class GeoContext:
    """What a provider may need beyond the raw coordinates — mirrors
    `FilterContext`/`AnalysisContext`'s same reasoning. `conn` and `location` are
    only used by a curated-data provider (reading `knowledge_entries`); a real
    routing-API provider would ignore both and just make its own HTTP call.
    """

    conn: sqlite3.Connection | None = None
    location: str | None = None


class GeoProvider(ABC):
    provider_id: str

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap, side-effect-free check — mirrors `Provider.is_available()`
        exactly. Never makes the actual calculation itself.
        """
        raise NotImplementedError

    @abstractmethod
    def metadata(self) -> GeoProviderMetadata:
        raise NotImplementedError

    @abstractmethod
    def calculate_distance(
        self,
        origin: Coordinates,
        destination: Coordinates,
        mode: TravelMode,
        context: GeoContext,
    ) -> GeoResult:
        """Raises `GeoCalculationError` (never a bare exception) if this provider
        cannot produce a result for `mode` — `GeographicEngine`/the calculators treat
        that as "try the next provider," exactly like `ProviderRouter.run_with_fallback()`.
        """
        raise NotImplementedError

    @abstractmethod
    def find_nearby(self, origin: Coordinates, category: str, context: GeoContext) -> list[NearbyPlace]:
        """Returns every known place of `category` near `origin` — an empty list
        (never a fabricated one) when this provider has no evidence for that
        category/location.
        """
        raise NotImplementedError
