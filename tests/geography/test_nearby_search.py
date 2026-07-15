"""Unit tests for NearbySearch — src/geography/nearby_search.py, against the real
`haversine` provider and a real (temp) database with curated `knowledge_entries`.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.geography.base_provider import GeoContext
from src.geography.cache import GeoCache
from src.geography.nearby_search import NEARBY_CATEGORIES, NearbySearch
from src.storage import reference_data_repository
from src.storage.database import Database
from src.storage.models import KnowledgeEntry

_ORIGIN = (40.7128, -74.0060)


class NearbySearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    id=None, category="nearby_amenities", key="Manhattan:supermarket",
                    value_json=json.dumps({"count": 4}), source="manual",
                    updated_at=datetime.now(timezone.utc),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_all_17_mission_categories_are_present(self) -> None:
        expected = {
            "supermarket", "pharmacy", "hospital", "clinic", "university", "school", "park",
            "restaurant", "gym", "bank", "atm", "parking", "bus_stop", "metro_station",
            "train_station", "coworking_space", "shopping_center",
        }
        self.assertEqual(set(NEARBY_CATEGORIES), expected)
        self.assertEqual(len(NEARBY_CATEGORIES), 17)

    def test_curated_category_returns_real_count(self) -> None:
        search = NearbySearch()
        with self.db.transaction() as conn:
            places = search.find_nearby(_ORIGIN, "supermarket", GeoContext(conn=conn, location="Manhattan"))
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0].count, 4)
        self.assertIsNotNone(places[0].confidence)

    def test_uncurated_category_is_honest_not_fabricated(self) -> None:
        search = NearbySearch()
        with self.db.transaction() as conn:
            places = search.find_nearby(_ORIGIN, "hospital", GeoContext(conn=conn, location="Manhattan"))
        self.assertEqual(len(places), 1)
        self.assertIsNone(places[0].count)
        self.assertTrue(places[0].warnings)

    def test_no_context_returns_empty_list(self) -> None:
        search = NearbySearch()
        places = search.find_nearby(_ORIGIN, "supermarket", GeoContext())
        self.assertEqual(places, [])

    def test_find_nearby_all_categories_covers_every_category(self) -> None:
        search = NearbySearch()
        with self.db.transaction() as conn:
            results = search.find_nearby_all_categories(_ORIGIN, GeoContext(conn=conn, location="Manhattan"))
        self.assertEqual(set(results.keys()), set(NEARBY_CATEGORIES))

    def test_repeated_search_uses_the_cache(self) -> None:
        cache = GeoCache()
        search = NearbySearch(cache=cache)
        with self.db.transaction() as conn:
            context = GeoContext(conn=conn, location="Manhattan")
            search.find_nearby(_ORIGIN, "supermarket", context)
            self.assertEqual(len(cache), 1)
            search.find_nearby(_ORIGIN, "supermarket", context)
            self.assertEqual(len(cache), 1)  # cache hit, not a second entry


if __name__ == "__main__":
    unittest.main()
