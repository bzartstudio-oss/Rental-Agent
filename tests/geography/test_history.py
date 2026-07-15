"""Unit tests for GeoHistory — src/geography/history.py + migration 0006's
`geo_enrichment_history` table.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.geography.history import (
    get_geo_history_for_apartment,
    get_geo_history_for_search,
    record_geo_enrichment,
    summarize_enrichment,
)
from src.geography.models import GeoEnrichment, GeoResult, TravelMode
from src.storage import search_repository
from src.storage.database import Database
from src.storage.models import SearchRequestRecord

_NOW = datetime.now(timezone.utc)


def _result(mode: TravelMode, provider_id: str = "haversine", method: str = "haversine") -> GeoResult:
    return GeoResult(
        origin=(0, 0), destination=(0, 1), mode=mode, distance_km=2.5, travel_time_minutes=30.0,
        confidence=0.7, computed_at=_NOW, provider_id=provider_id, calculation_method=method,
    )


class GeoHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(
                    id="search-1", created_at=_NOW,
                    criteria_json=json.dumps({"location": "x", "criteria": {}}),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_summarize_enrichment_is_json_safe(self) -> None:
        import json

        enrichment = GeoEnrichment(
            apartment_id="apt-1", distances={TravelMode.WALKING: _result(TravelMode.WALKING)},
        )
        json.dumps(summarize_enrichment(enrichment))  # must not raise

    def test_record_and_retrieve_for_apartment(self) -> None:
        enrichment = GeoEnrichment(
            apartment_id="apt-1", distances={TravelMode.STRAIGHT_LINE: _result(TravelMode.STRAIGHT_LINE)},
        )
        with self.db.transaction() as conn:
            record_geo_enrichment(conn, enrichment, recorded_at=_NOW, search_id="search-1")
            history = get_geo_history_for_apartment(conn, "apt-1")

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].apartment_id, "apt-1")
        self.assertEqual(history[0].provider_id, "haversine")
        self.assertEqual(history[0].calculation_method, "haversine")
        self.assertEqual(history[0].search_id, "search-1")

    def test_provider_id_and_method_are_derived_never_hardcoded(self) -> None:
        """The engine must remain provider-independent — `record_geo_enrichment`
        reads `provider_id`/`calculation_method` from the enrichment's own results,
        never from a literal passed by the caller.
        """
        enrichment = GeoEnrichment(
            apartment_id="apt-1",
            distances={
                TravelMode.STRAIGHT_LINE: _result(TravelMode.STRAIGHT_LINE, method="haversine"),
                TravelMode.WALKING: _result(TravelMode.WALKING, method="haversine+estimated_speed(5km/h)"),
            },
        )
        with self.db.transaction() as conn:
            record_geo_enrichment(conn, enrichment, recorded_at=_NOW)
            history = get_geo_history_for_apartment(conn, "apt-1")
        self.assertEqual(history[0].calculation_method, "mixed")  # two distinct methods, honestly labeled

    def test_no_history_for_an_unrelated_apartment(self) -> None:
        with self.db.transaction() as conn:
            history = get_geo_history_for_apartment(conn, "does-not-exist")
        self.assertEqual(history, [])

    def test_get_history_for_search(self) -> None:
        e1 = GeoEnrichment(apartment_id="apt-1", distances={TravelMode.WALKING: _result(TravelMode.WALKING)})
        e2 = GeoEnrichment(apartment_id="apt-2", distances={TravelMode.WALKING: _result(TravelMode.WALKING)})
        with self.db.transaction() as conn:
            record_geo_enrichment(conn, e1, recorded_at=_NOW, search_id="search-1")
            record_geo_enrichment(conn, e2, recorded_at=_NOW, search_id="search-1")
            history = get_geo_history_for_search(conn, "search-1")
        self.assertEqual(len(history), 2)

    def test_empty_enrichment_records_none_confidence(self) -> None:
        enrichment = GeoEnrichment(apartment_id="apt-1")
        with self.db.transaction() as conn:
            record_geo_enrichment(conn, enrichment, recorded_at=_NOW)
            history = get_geo_history_for_apartment(conn, "apt-1")
        self.assertIsNone(history[0].confidence)
        self.assertEqual(history[0].provider_id, "unknown")


if __name__ == "__main__":
    unittest.main()
