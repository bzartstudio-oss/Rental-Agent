"""Tests for src/analysis/engine.py — AnalysisEngine, the entry point core/agent.py holds."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.engine import AnalysisEngine
from src.storage.database import Database
from src.storage.models import Apartment


def _make_apartment(apartment_id: str) -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id=apartment_id, platform_id="test_platform", platform_listing_id=apartment_id, title="A Nice Place",
        url=f"https://example.com/{apartment_id}", current_price=1000.0, current_status="available",
        first_seen_at=now, last_seen_at=now,
    )


class AnalysisEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_analyzes_every_apartment_and_returns_a_result_per_id(self) -> None:
        engine = AnalysisEngine()
        apartments = [_make_apartment("apt-1"), _make_apartment("apt-2")]

        with self.db.transaction() as conn:
            results = engine.analyze(conn, apartments, location="Example City", search_id="search-1")

        self.assertEqual(set(results), {"apt-1", "apt-2"})
        self.assertEqual(results["apt-1"].apartment_id, "apt-1")
        self.assertEqual(results["apt-1"].search_id, "search-1")

    def test_every_apartment_in_one_run_shares_the_same_computed_at(self) -> None:
        engine = AnalysisEngine()
        apartments = [_make_apartment("apt-1"), _make_apartment("apt-2")]

        with self.db.transaction() as conn:
            results = engine.analyze(conn, apartments, location="Example City")

        self.assertEqual(results["apt-1"].computed_at, results["apt-2"].computed_at)

    def test_search_id_defaults_to_none(self) -> None:
        engine = AnalysisEngine()
        with self.db.transaction() as conn:
            results = engine.analyze(conn, [_make_apartment("apt-1")], location="Example City")

        self.assertIsNone(results["apt-1"].search_id)

    def test_empty_apartment_list_returns_empty_dict(self) -> None:
        engine = AnalysisEngine()
        with self.db.transaction() as conn:
            results = engine.analyze(conn, [], location="Example City")
        self.assertEqual(results, {})


if __name__ == "__main__":
    unittest.main()
