"""Phase 4 exit-criteria test (docs/10_Roadmap.md): one real SearchRequest, run through
the real orchestrator against the real demo_platform connector (a real Playwright fetch of
a real local fixture, really parsed), produces real rows in apartments,
apartment_price_history, apartment_availability_history, and apartment_images.

Also covers Phase 5 (ranking + report persisted/generated as part of the same run()).
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.search.search_request import SearchRequest
from src.storage import apartment_repository
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors


class RentalResearchAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.output_dir = Path(self._tmp_dir.name) / "output"
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform",
                    name="Demo Platform (reference/demo connector, not real)",
                    base_url="local-fixture",
                    connector_module="src.connectors.demo_platform",
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                ),
            )

        self.agent = RentalResearchAgent(self.db, output_dir=self.output_dir)

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_run_produces_real_apartment_and_history_rows(self) -> None:
        request = SearchRequest(location="Example City")

        result = self.agent.run(request)

        self.assertEqual(len(result.apartments), 3)

        with self.db.transaction() as conn:
            for apartment in result.apartments:
                fetched = apartment_repository.get_apartment(conn, apartment.id)
                price_history = apartment_repository.get_price_history(conn, apartment.id)
                availability_history = apartment_repository.get_availability_history(conn, apartment.id)
                images = apartment_repository.get_images(conn, apartment.id)

                self.assertIsNotNone(fetched)
                self.assertEqual(len(price_history), 1)
                self.assertEqual(len(availability_history), 1)
                self.assertEqual(len(images), 1)

    def test_run_persists_the_search_request_itself(self) -> None:
        from src.storage import search_repository

        request = SearchRequest(location="Example City", criteria={"max_price": 2000.0})
        self.agent.run(request)

        with self.db.transaction() as conn:
            record = search_repository.get_search_request(conn, request.id)

        self.assertIsNotNone(record)
        self.assertIn("Example City", record.criteria_json)

    def test_a_broken_connector_does_not_crash_the_whole_run(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="broken_platform",
                    name="Broken Platform",
                    base_url="does-not-matter",
                    connector_module="src.connectors.does_not_exist_module",
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                ),
            )

        request = SearchRequest(location="Example City")
        result = self.agent.run(request)  # must not raise

        self.assertEqual(len(result.apartments), 3)  # demo_platform's results still came through

    def test_run_ranks_results_and_writes_search_results_rows(self) -> None:
        from src.storage import search_repository

        request = SearchRequest(location="Example City", criteria={"max_price": 2000.0})
        self.agent.run(request)

        with self.db.transaction() as conn:
            results = search_repository.get_search_results(conn, request.id)

        # demo-003 is priced above the max_price=2000 cutoff, so only 2 should survive
        self.assertEqual(len(results), 2)
        self.assertEqual([r.rank for r in results], [1, 2])
        # cheaper apartment scores higher and ranks first
        self.assertLessEqual(results[0].price_at_search, results[1].price_at_search)

    def test_run_generates_a_real_html_report(self) -> None:
        request = SearchRequest(location="Example City")

        result = self.agent.run(request)

        self.assertTrue(result.report_path.exists())
        content = result.report_path.read_text(encoding="utf-8")
        self.assertIn("Rental Search Report", content)
        self.assertIn("Example City", content)
        self.assertIn("Original listing", content)


if __name__ == "__main__":
    unittest.main()
