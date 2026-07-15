"""Performance regression test for the Deep Analysis Engine — analyzing many apartments
(all 11 registered analyzers run per apartment) must stay fast, since this runs on
every search's full result set, not just a handful of listings.
"""

import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.engine import AnalysisEngine
from src.storage.database import Database
from src.storage.models import Apartment


class AnalysisEnginePerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_analyzing_hundreds_of_apartments_stays_fast(self) -> None:
        now = datetime.now(timezone.utc)
        apartments = [
            Apartment(
                id=f"apt-{i}", platform_id="test_platform", platform_listing_id=f"listing-{i}",
                title=f"Listing {i}", url=f"https://example.com/{i}", current_price=1000.0,
                current_status="available", first_seen_at=now, last_seen_at=now,
            )
            for i in range(300)
        ]

        engine = AnalysisEngine()
        started = time.perf_counter()
        with self.db.transaction() as conn:
            results = engine.analyze(conn, apartments, location="Example City")
        elapsed = time.perf_counter() - started

        self.assertEqual(len(results), 300)
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
