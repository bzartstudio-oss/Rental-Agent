"""`DistanceCalculator`, `TravelTimeCalculator`, `RouteCalculator` — the three named
calculation facades the mission asks for, all sharing one execution core
(`DistanceCalculator`) and one optional `GeoCache`. See
docs/26_Geographic_Intelligence.md "Routing".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.geography.base_provider import GeoContext
from src.geography.cache import GeoCache
from src.geography.factory import GeoProviderFactory
from src.geography.models import Coordinates, GeoResult, TravelMode


class DistanceCalculator:
    """The one place that actually resolves a provider and (optionally) caches a
    calculation — `TravelTimeCalculator`/`RouteCalculator` both delegate here rather
    than resolving a provider or touching the cache themselves.
    """

    def __init__(self, cache: GeoCache | None = None, provider_id: str | None = None) -> None:
        self._cache = cache
        self._provider_id = provider_id

    def calculate(
        self,
        origin: Coordinates,
        destination: Coordinates,
        mode: TravelMode,
        context: GeoContext | None = None,
    ) -> GeoResult:
        context = context or GeoContext()
        provider = (
            GeoProviderFactory.get(self._provider_id)
            if self._provider_id is not None
            else GeoProviderFactory.get_best_available()
        )

        cache_key = GeoCache.make_key("distance", provider.provider_id, origin, destination, mode.value)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        result = provider.calculate_distance(origin, destination, mode, context)

        if self._cache is not None:
            self._cache.set(cache_key, result)
        return result


class TravelTimeCalculator:
    """A thin, semantically distinct facade over `DistanceCalculator` — our one
    built-in provider computes distance and travel time together from the same
    physical model (see `providers/haversine_provider.py`), so there is nothing
    genuinely separate to compute here yet; this class exists so travel-time-focused
    callers (and a future provider that *can* compute them independently, e.g. one
    accounting for real-time traffic) have their own, stable entry point without
    duplicating `DistanceCalculator`'s provider-resolution/caching logic.
    """

    def __init__(self, distance_calculator: DistanceCalculator) -> None:
        self._distance_calculator = distance_calculator

    def calculate(
        self,
        origin: Coordinates,
        destination: Coordinates,
        mode: TravelMode,
        context: GeoContext | None = None,
    ) -> GeoResult:
        return self._distance_calculator.calculate(origin, destination, mode, context)


@dataclass
class RouteSegment:
    origin: Coordinates
    destination: Coordinates
    mode: TravelMode
    distance_km: float | None
    travel_time_minutes: float | None


@dataclass
class Route:
    """A route is a list of segments so a future real-routing provider (with real
    waypoints/turns) fits this same shape — today's `RouteCalculator` always
    produces exactly one segment (a straight line, since no routing API is
    integrated), never a fabricated multi-waypoint path.
    """

    segments: list[RouteSegment] = field(default_factory=list)
    total_distance_km: float | None = None
    total_travel_time_minutes: float | None = None
    provider_id: str = ""
    calculation_method: str = ""
    confidence: float = 0.0
    computed_at: datetime | None = None


class RouteCalculator:
    """Builds a single-segment "route" from `DistanceCalculator`'s own output.
    Honestly not a real routing engine — see `Route`'s docstring — but a real,
    working facade a future multi-segment-capable `GeoProvider` slots into without
    any change to this class's public shape.
    """

    def __init__(self, distance_calculator: DistanceCalculator) -> None:
        self._distance_calculator = distance_calculator

    def calculate_route(
        self,
        origin: Coordinates,
        destination: Coordinates,
        mode: TravelMode,
        context: GeoContext | None = None,
    ) -> Route:
        result = self._distance_calculator.calculate(origin, destination, mode, context)
        segment = RouteSegment(
            origin=origin, destination=destination, mode=mode,
            distance_km=result.distance_km, travel_time_minutes=result.travel_time_minutes,
        )
        return Route(
            segments=[segment],
            total_distance_km=result.distance_km,
            total_travel_time_minutes=result.travel_time_minutes,
            provider_id=result.provider_id,
            calculation_method=result.calculation_method,
            confidence=result.confidence,
            computed_at=result.computed_at,
        )
