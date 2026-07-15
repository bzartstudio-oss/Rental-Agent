"""Unit tests for the shared geography data shapes — src/geography/models.py."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.geography.models import GeoEnrichment, GeoResult, NearbyPlace, TravelMode


class TravelModeTests(unittest.TestCase):
    def test_every_mission_mode_is_present(self) -> None:
        expected = {"straight_line", "walking", "cycling", "driving", "public_transport"}
        self.assertEqual({mode.value for mode in TravelMode}, expected)


class GeoResultTests(unittest.TestCase):
    def test_missing_travel_time_is_none_not_zero(self) -> None:
        result = GeoResult(
            origin=(0, 0), destination=(0, 1), mode=TravelMode.STRAIGHT_LINE, distance_km=1.0,
            travel_time_minutes=None, confidence=1.0, computed_at=datetime.now(timezone.utc),
            provider_id="haversine", calculation_method="haversine",
        )
        self.assertIsNone(result.travel_time_minutes)


class NearbyPlaceTests(unittest.TestCase):
    def test_warnings_default_to_empty_list_not_none(self) -> None:
        place = NearbyPlace(
            category="supermarket", count=1, distance_km=None, travel_time_minutes=None,
            confidence=0.8, computed_at=datetime.now(timezone.utc), provider_id="haversine",
            calculation_method="knowledge_entries",
        )
        self.assertEqual(place.warnings, [])


class GeoEnrichmentTests(unittest.TestCase):
    def test_defaults_are_empty_not_none(self) -> None:
        enrichment = GeoEnrichment(apartment_id="apt-1")
        self.assertEqual(enrichment.distances, {})
        self.assertEqual(enrichment.nearby, {})

    def test_two_enrichments_do_not_share_mutable_defaults(self) -> None:
        e1 = GeoEnrichment(apartment_id="apt-1")
        e2 = GeoEnrichment(apartment_id="apt-2")
        e1.distances["x"] = "not a real result, just checking isolation"
        self.assertEqual(e2.distances, {})


if __name__ == "__main__":
    unittest.main()
