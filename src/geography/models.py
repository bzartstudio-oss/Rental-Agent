"""Shared shapes for the Geographic Intelligence Engine — every distance/travel-time/
nearby-search result uses one of these, regardless of which `GeoProvider` produced
it. See docs/26_Geographic_Intelligence.md "Architecture".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TravelMode(str, Enum):
    STRAIGHT_LINE = "straight_line"
    WALKING = "walking"
    CYCLING = "cycling"
    DRIVING = "driving"
    PUBLIC_TRANSPORT = "public_transport"


Coordinates = tuple[float, float]  # (latitude, longitude)


@dataclass
class GeoResult:
    """One distance/travel-time calculation between two points. Every field the
    mission asks every result to carry — distance, travel time, confidence,
    timestamp, provider, calculation method — is here, never optional-by-omission
    (a field that doesn't apply is `None`, not missing).
    """

    origin: Coordinates
    destination: Coordinates
    mode: TravelMode
    distance_km: float | None
    travel_time_minutes: float | None
    confidence: float
    computed_at: datetime
    provider_id: str
    calculation_method: str


@dataclass
class NearbyPlace:
    """One nearby-search result for one category at one location. Curated,
    count-based evidence (see `providers/haversine_provider.py`) has no per-place
    coordinates, so `distance_km`/`travel_time_minutes` are honestly `None` — a real
    POI-level provider (Google Places, OSM Overpass, ...) would populate them; this
    shape doesn't change either way.
    """

    category: str
    count: int | None
    distance_km: float | None
    travel_time_minutes: float | None
    confidence: float | None
    computed_at: datetime
    provider_id: str
    calculation_method: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class GeoEnrichment:
    """The Geographic Intelligence Engine's entire output for one apartment — a
    read-only bundle, never written back onto the `Apartment` it describes (see
    `GeographicEngine.enrich()`'s own docstring for why).
    """

    apartment_id: str
    distances: dict[TravelMode, GeoResult] = field(default_factory=dict)
    nearby: dict[str, list[NearbyPlace]] = field(default_factory=dict)
    computed_at: datetime | None = None
