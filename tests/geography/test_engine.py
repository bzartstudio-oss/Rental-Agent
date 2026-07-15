"""Unit + Integration tests for GeographicEngine — src/geography/engine.py."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.geography.base_provider import GeoContext
from src.geography.engine import GeographicEngine
from src.geography.models import TravelMode
from src.storage import reference_data_repository
from src.storage.database import Database
from src.storage.models import Apartment, KnowledgeEntry


def _make_apartment(apartment_id: str, latitude: float | None, longitude: float | None) -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id=apartment_id, platform_id="demo", platform_listing_id=apartment_id, title="Test",
        url="http://example.test", current_price=1000, current_status="active",
        first_seen_at=now, last_seen_at=now, latitude=latitude, longitude=longitude,
    )


class GeographicEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    id=None, category="city_center", key="Manhattan",
                    value_json=json.dumps({"latitude": 40.7580, "longitude": -73.9855}),
                    source="manual", updated_at=datetime.now(timezone.utc),
                ),
            )
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    id=None, category="nearby_amenities", key="Manhattan:supermarket",
                    value_json=json.dumps({"count": 3}), source="manual",
                    updated_at=datetime.now(timezone.utc),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_apartment_with_no_coordinates_gets_an_honestly_empty_enrichment(self) -> None:
        """"It NEVER modifies original apartment data" and never fabricates evidence
        that doesn't exist — an apartment with no coordinates gets no distances.
        """
        engine = GeographicEngine()
        apartment = _make_apartment("apt-no-coords", None, None)
        with self.db.transaction() as conn:
            enrichment = engine.enrich(apartment, GeoContext(conn=conn, location="Manhattan"))
        self.assertEqual(enrichment.distances, {})
        self.assertEqual(apartment.latitude, None)  # original apartment untouched

    def test_apartment_with_coordinates_but_no_reference_point_gets_no_distances(self) -> None:
        engine = GeographicEngine()
        apartment = _make_apartment("apt-1", 40.7128, -74.0060)
        with self.db.transaction() as conn:
            enrichment = engine.enrich(apartment, GeoContext(conn=conn, location="Nowhereville"))
        self.assertEqual(enrichment.distances, {})

    def test_full_enrichment_computes_every_travel_mode(self) -> None:
        engine = GeographicEngine()
        apartment = _make_apartment("apt-1", 40.7128, -74.0060)
        with self.db.transaction() as conn:
            enrichment = engine.enrich(apartment, GeoContext(conn=conn, location="Manhattan"))

        self.assertEqual(set(enrichment.distances.keys()), set(TravelMode))
        for mode, result in enrichment.distances.items():
            self.assertIsNotNone(result.distance_km)
            self.assertIsNotNone(result.confidence)

    def test_enrichment_never_mutates_the_apartment(self) -> None:
        engine = GeographicEngine()
        apartment = _make_apartment("apt-1", 40.7128, -74.0060)
        original_lat, original_lon = apartment.latitude, apartment.longitude
        with self.db.transaction() as conn:
            engine.enrich(apartment, GeoContext(conn=conn, location="Manhattan"))
        self.assertEqual(apartment.latitude, original_lat)
        self.assertEqual(apartment.longitude, original_lon)
        self.assertFalse(hasattr(apartment, "distances"))
        self.assertFalse(hasattr(apartment, "geo_enrichment"))

    def test_enrichment_includes_nearby_results(self) -> None:
        engine = GeographicEngine()
        apartment = _make_apartment("apt-1", 40.7128, -74.0060)
        with self.db.transaction() as conn:
            enrichment = engine.enrich(apartment, GeoContext(conn=conn, location="Manhattan"))
        self.assertEqual(enrichment.nearby["supermarket"][0].count, 3)
        self.assertIsNone(enrichment.nearby["hospital"][0].count)  # honest, no fabrication

    def test_enrich_many_keys_results_by_apartment_id(self) -> None:
        engine = GeographicEngine()
        apartments = [_make_apartment("apt-1", 40.7128, -74.0060), _make_apartment("apt-2", None, None)]
        with self.db.transaction() as conn:
            enrichments = engine.enrich_many(apartments, GeoContext(conn=conn, location="Manhattan"))
        self.assertEqual(set(enrichments.keys()), {"apt-1", "apt-2"})
        self.assertTrue(enrichments["apt-1"].distances)
        self.assertFalse(enrichments["apt-2"].distances)


if __name__ == "__main__":
    unittest.main()
