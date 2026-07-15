"""Distance + Travel Time tests for DistanceCalculator/TravelTimeCalculator/
RouteCalculator — src/geography/calculators.py. Exercises the real, registered
`haversine` provider (no mocking) so distances are checked against real, known
straight-line values.
"""

from __future__ import annotations

import unittest

from src.geography.base_provider import GeoContext
from src.geography.cache import GeoCache
from src.geography.calculators import DistanceCalculator, RouteCalculator, TravelTimeCalculator
from src.geography.models import TravelMode

# Statue of Liberty to Empire State Building — real-world straight-line distance is
# well-documented (~8.5 km), used here as a sanity bound, not an exact literal.
_ORIGIN = (40.6892, -74.0445)
_DESTINATION = (40.7484, -73.9857)


class DistanceCalculatorTests(unittest.TestCase):
    def test_straight_line_distance_is_real_haversine_math(self) -> None:
        calc = DistanceCalculator()
        result = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.STRAIGHT_LINE)
        self.assertAlmostEqual(result.distance_km, 8.4, delta=1.0)
        self.assertEqual(result.confidence, 1.0)
        self.assertIsNone(result.travel_time_minutes)

    def test_every_result_carries_all_mandated_fields(self) -> None:
        """"Every result must include: Distance, Travel Time, Confidence, Timestamp,
        Provider, Calculation Method" (the mission's own words).
        """
        calc = DistanceCalculator()
        result = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.WALKING)
        self.assertIsNotNone(result.distance_km)
        self.assertIsNotNone(result.travel_time_minutes)
        self.assertIsNotNone(result.confidence)
        self.assertIsNotNone(result.computed_at)
        self.assertEqual(result.provider_id, "haversine")
        self.assertTrue(result.calculation_method)

    def test_walking_is_slower_than_driving_for_the_same_distance(self) -> None:
        calc = DistanceCalculator()
        walking = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.WALKING)
        driving = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.DRIVING)
        self.assertGreater(walking.travel_time_minutes, driving.travel_time_minutes)

    def test_estimated_travel_time_confidence_is_lower_than_exact_distance(self) -> None:
        """Honesty check: a speed-based estimate must never claim the same certainty
        as the exact haversine distance calculation.
        """
        calc = DistanceCalculator()
        straight_line = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.STRAIGHT_LINE)
        walking = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.WALKING)
        self.assertLess(walking.confidence, straight_line.confidence)

    def test_repeated_calculation_uses_the_cache(self) -> None:
        cache = GeoCache()
        calc = DistanceCalculator(cache=cache)
        self.assertEqual(len(cache), 0)
        result1 = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.WALKING)
        self.assertEqual(len(cache), 1)
        result2 = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.WALKING)
        self.assertEqual(len(cache), 1)  # second call is a cache hit, not a second entry
        self.assertEqual(result1, result2)

    def test_no_cache_means_every_call_recomputes(self) -> None:
        calc = DistanceCalculator(cache=None)
        result1 = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.STRAIGHT_LINE)
        result2 = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.STRAIGHT_LINE)
        self.assertEqual(result1.distance_km, result2.distance_km)
        self.assertNotEqual(result1.computed_at, result2.computed_at)  # genuinely recomputed


class TravelTimeCalculatorTests(unittest.TestCase):
    def test_delegates_to_the_distance_calculator(self) -> None:
        calc = TravelTimeCalculator(DistanceCalculator())
        result = calc.calculate(_ORIGIN, _DESTINATION, TravelMode.PUBLIC_TRANSPORT)
        self.assertIsNotNone(result.travel_time_minutes)
        self.assertEqual(result.mode, TravelMode.PUBLIC_TRANSPORT)


class RouteCalculatorTests(unittest.TestCase):
    def test_route_has_exactly_one_segment_honestly(self) -> None:
        """No real routing API is integrated (the mission's own "Do not hardcode any
        map provider" constraint) — a route is honestly a single straight-line
        segment, never a fabricated multi-waypoint path.
        """
        calc = RouteCalculator(DistanceCalculator())
        route = calc.calculate_route(_ORIGIN, _DESTINATION, TravelMode.DRIVING)
        self.assertEqual(len(route.segments), 1)
        self.assertEqual(route.segments[0].origin, _ORIGIN)
        self.assertEqual(route.segments[0].destination, _DESTINATION)
        self.assertEqual(route.total_distance_km, route.segments[0].distance_km)

    def test_route_carries_confidence_and_provider(self) -> None:
        calc = RouteCalculator(DistanceCalculator())
        route = calc.calculate_route(_ORIGIN, _DESTINATION, TravelMode.CYCLING)
        self.assertEqual(route.provider_id, "haversine")
        self.assertTrue(route.calculation_method)
        self.assertIsNotNone(route.confidence)
        self.assertIsNotNone(route.computed_at)


if __name__ == "__main__":
    unittest.main()
