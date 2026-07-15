"""The Geographic Intelligence Engine — a modular, provider-independent system for
calculating spatial relationships between apartments and points of interest. See
docs/26_Geographic_Intelligence.md.

Importing this package imports `geography.providers`, which is what runs every
built-in geo provider's `register_geo_provider(...)` call. Public API re-exported
here so callers don't need to know this package's internal file layout — mirrors
`src.filter_engine`/`src.providers`'s own re-export shape.
"""

from __future__ import annotations

from src.geography import providers as _providers  # noqa: F401 — import for self-registration side effect
from src.geography.base_provider import GeoContext, GeoProvider
from src.geography.cache import GeoCache
from src.geography.calculators import DistanceCalculator, Route, RouteCalculator, RouteSegment, TravelTimeCalculator
from src.geography.engine import GeographicEngine
from src.geography.exceptions import GeoCalculationError, GeoException, GeoProviderConfigurationError
from src.geography.factory import GeoProviderFactory
from src.geography.history import GeoHistoryEntry, get_geo_history_for_apartment, get_geo_history_for_search, record_geo_enrichment
from src.geography.metadata import GeoProviderMetadata
from src.geography.models import Coordinates, GeoEnrichment, GeoResult, NearbyPlace, TravelMode
from src.geography.nearby_search import NEARBY_CATEGORIES, NearbySearch
from src.geography.registry import GeoProviderRegistry, register_geo_provider
from src.geography.statistics import GeoStatistics, compute_geo_statistics

__all__ = [
    "GeoContext",
    "GeoProvider",
    "GeoCache",
    "DistanceCalculator",
    "Route",
    "RouteCalculator",
    "RouteSegment",
    "TravelTimeCalculator",
    "GeographicEngine",
    "GeoException",
    "GeoCalculationError",
    "GeoProviderConfigurationError",
    "GeoProviderFactory",
    "GeoHistoryEntry",
    "record_geo_enrichment",
    "get_geo_history_for_apartment",
    "get_geo_history_for_search",
    "GeoProviderMetadata",
    "Coordinates",
    "GeoEnrichment",
    "GeoResult",
    "NearbyPlace",
    "TravelMode",
    "NEARBY_CATEGORIES",
    "NearbySearch",
    "GeoProviderRegistry",
    "register_geo_provider",
    "GeoStatistics",
    "compute_geo_statistics",
]
