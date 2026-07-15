"""Tests for src/analysis/analyzers/public_transport.py."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.analyzers.public_transport import PublicTransportAnalyzer
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


class PublicTransportAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _context(self, conn) -> AnalysisContext:
        return AnalysisContext(conn=conn, location="Example City", computed_at=datetime.now(timezone.utc))

    def test_no_evidence_without_coordinates_or_curated_stop(self) -> None:
        apartment = _make_apartment()
        with self.db.transaction() as conn:
            result = PublicTransportAnalyzer().analyze(apartment, self._context(conn))

        self.assertIsNone(result.score)
        self.assertIn("no coordinates", result.warnings[0].lower())

    def test_apartment_at_the_stop_scores_maximum(self) -> None:
        apartment = _make_apartment(latitude=40.0, longitude=-3.0)
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="public_transport", key="Example City",
                    value_json=json.dumps({"latitude": 40.0, "longitude": -3.0, "stop_name": "Central Station"}),
                    updated_at=datetime.now(timezone.utc),
                ),
            )
            result = PublicTransportAnalyzer().analyze(apartment, self._context(conn))

        self.assertEqual(result.score, 1.0)
        self.assertIn("Central Station", result.evidence[0])


if __name__ == "__main__":
    unittest.main()
