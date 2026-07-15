"""Unit tests for HaversineGeoProvider — src/geography/providers/haversine_provider.py,
the one built-in, real `GeoProvider`.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.geography.base_provider import GeoContext
from src.geography.exceptions import GeoCalculationError
from src.geography.models import TravelMode
from src.geography.providers.haversine_provider import HaversineGeoProvider
from src.storage import reference_data_repository
from src.storage.database import Database
from src.storage.models import KnowledgeEntry

_ORIGIN = (40.7128, -74.0060)
_DESTINATION = (40.7306, -73.9352)


class HaversineGeoProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = HaversineGeoProvider()

    def test_is_available_is_always_true(self) -> None:
        self.assertTrue(self.provider.is_available())

    def test_metadata_declares_no_real_routing(self) -> None:
        metadata = self.provider.metadata()
        self.assertFalse(metadata.supports_real_routing)
        self.assertEqual(set(metadata.supported_modes), {mode.value for mode in TravelMode})
        self.assertEqual(len(metadata.supported_nearby_categories), 17)

    def test_straight_line_distance_matches_known_real_value(self) -> None:
        result = self.provider.calculate_distance(_ORIGIN, _DESTINATION, TravelMode.STRAIGHT_LINE, GeoContext())
        self.assertAlmostEqual(result.distance_km, 6.28, delta=0.1)
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.calculation_method, "haversine")

    def test_walking_travel_time_is_distance_over_walking_speed(self) -> None:
        result = self.provider.calculate_distance(_ORIGIN, _DESTINATION, TravelMode.WALKING, GeoContext())
        expected_minutes = (result.distance_km / 5.0) * 60
        self.assertAlmostEqual(result.travel_time_minutes, expected_minutes, places=5)

    def test_each_mode_uses_a_distinct_documented_speed(self) -> None:
        times = {
            mode: self.provider.calculate_distance(_ORIGIN, _DESTINATION, mode, GeoContext()).travel_time_minutes
            for mode in (TravelMode.WALKING, TravelMode.CYCLING, TravelMode.DRIVING, TravelMode.PUBLIC_TRANSPORT)
        }
        # Faster average speed -> less travel time for the same distance.
        self.assertGreater(times[TravelMode.WALKING], times[TravelMode.CYCLING])
        self.assertGreater(times[TravelMode.CYCLING], times[TravelMode.DRIVING])

    def test_invalid_coordinates_raise_geo_calculation_error(self) -> None:
        with self.assertRaises(GeoCalculationError):
            self.provider.calculate_distance((None, None), _DESTINATION, TravelMode.STRAIGHT_LINE, GeoContext())

    def test_find_nearby_without_context_returns_empty_list(self) -> None:
        places = self.provider.find_nearby(_ORIGIN, "supermarket", GeoContext())
        self.assertEqual(places, [])

    def test_find_nearby_with_curated_data_is_real_not_fabricated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Database(db_path=Path(tmp_dir) / "test.db")
            with db.transaction() as conn:
                reference_data_repository.upsert_knowledge_entry(
                    conn,
                    KnowledgeEntry(
                        id=None, category="nearby_amenities", key="Manhattan:pharmacy",
                        value_json=json.dumps({"count": 2}), source="manual",
                        updated_at=datetime.now(timezone.utc),
                    ),
                )
                places = self.provider.find_nearby(_ORIGIN, "pharmacy", GeoContext(conn=conn, location="Manhattan"))
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0].count, 2)
        self.assertEqual(places[0].confidence, 0.8)
        self.assertEqual(places[0].warnings, [])

    def test_find_nearby_without_curated_data_is_honest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Database(db_path=Path(tmp_dir) / "test.db")
            with db.transaction() as conn:
                places = self.provider.find_nearby(_ORIGIN, "atm", GeoContext(conn=conn, location="Nowhereville"))
        self.assertEqual(len(places), 1)
        self.assertIsNone(places[0].count)
        self.assertIsNone(places[0].confidence)
        self.assertIn("Nowhereville", places[0].warnings[0])


if __name__ == "__main__":
    unittest.main()
