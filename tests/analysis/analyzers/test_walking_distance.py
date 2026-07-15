"""Tests for src/analysis/analyzers/walking_distance.py."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.analyzers.walking_distance import WalkingDistanceAnalyzer
from src.analysis.models import AnalysisContext
from src.storage import reference_data_repository
from src.storage.database import Database
from src.storage.models import Apartment, KnowledgeEntry


def _make_apartment(**overrides) -> Apartment:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="apt-1", platform_id="test_platform", platform_listing_id="listing-1", title="A",
        url="https://example.com/a", current_price=1000.0, current_status="available",
        first_seen_at=now, last_seen_at=now,
    )
    defaults.update(overrides)
    return Apartment(**defaults)


class WalkingDistanceAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _context(self, conn) -> AnalysisContext:
        return AnalysisContext(conn=conn, location="Example City", computed_at=datetime.now(timezone.utc))

    def test_no_evidence_without_apartment_coordinates(self) -> None:
        apartment = _make_apartment()  # latitude/longitude default None
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="city_center", key="Example City",
                    value_json=json.dumps({"latitude": 40.0, "longitude": -3.0}),
                    updated_at=datetime.now(timezone.utc),
                ),
            )
            result = WalkingDistanceAnalyzer().analyze(apartment, self._context(conn))

        self.assertIsNone(result.score)
        self.assertIn("no coordinates", result.warnings[0].lower())

    def test_no_evidence_without_a_curated_city_center(self) -> None:
        apartment = _make_apartment(latitude=40.0, longitude=-3.0)
        with self.db.transaction() as conn:
            result = WalkingDistanceAnalyzer().analyze(apartment, self._context(conn))

        self.assertIsNone(result.score)
        self.assertIn("no city center", result.warnings[0].lower())

    def test_apartment_at_the_reference_point_scores_maximum(self) -> None:
        apartment = _make_apartment(latitude=40.0, longitude=-3.0)
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="city_center", key="Example City",
                    value_json=json.dumps({"latitude": 40.0, "longitude": -3.0}),
                    updated_at=datetime.now(timezone.utc),
                ),
            )
            result = WalkingDistanceAnalyzer().analyze(apartment, self._context(conn))

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.confidence, 1.0)
        self.assertIn("0.00 km", result.evidence[0])

    def test_farther_apartments_score_lower(self) -> None:
        near = _make_apartment(id="apt-near", latitude=40.001, longitude=-3.0)
        far = _make_apartment(id="apt-far", latitude=40.1, longitude=-3.0)
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="city_center", key="Example City",
                    value_json=json.dumps({"latitude": 40.0, "longitude": -3.0}),
                    updated_at=datetime.now(timezone.utc),
                ),
            )
            context = self._context(conn)
            near_result = WalkingDistanceAnalyzer().analyze(near, context)
            far_result = WalkingDistanceAnalyzer().analyze(far, context)

        self.assertGreater(near_result.score, far_result.score)

    def test_beyond_max_scored_distance_floors_at_zero(self) -> None:
        very_far = _make_apartment(latitude=45.0, longitude=-3.0)  # ~555 km away
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="city_center", key="Example City",
                    value_json=json.dumps({"latitude": 40.0, "longitude": -3.0}),
                    updated_at=datetime.now(timezone.utc),
                ),
            )
            result = WalkingDistanceAnalyzer().analyze(very_far, self._context(conn))

        self.assertEqual(result.score, 0.0)  # never negative


if __name__ == "__main__":
    unittest.main()
