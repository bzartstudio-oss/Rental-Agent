"""v2.0 Step 3 integration test: RentalResearchAgent.run() must automatically create a
full Search Execution record (docs/17_Search_Memory.md) — this is the "Integration"
section of the mission, exercised through the real orchestrator and the real
demo_platform connector, the same way tests/core/test_agent.py proves the rest of the
pipeline.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.search.search_request import SearchRequest
from src.search_memory import search_memory_service
from src.storage import search_memory_repository, search_repository
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors


class SearchMemoryIntegrationTests(unittest.TestCase):
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
                    country="N/A (local fixture)",
                    homepage="local-fixture",
                    connector_available=True,
                    connector_name="demo_platform",
                    created_at=datetime.now(timezone.utc),
                ),
            )

        self.agent = RentalResearchAgent(self.db, output_dir=self.output_dir)

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_run_creates_a_complete_search_execution_record(self) -> None:
        request = SearchRequest(location="Example City")
        result = self.agent.run(request)

        with self.db.transaction() as conn:
            record = search_repository.get_search_request(conn, request.id)
            observed_ids = search_memory_repository.get_observed_apartment_ids(conn, request.id)

        self.assertIsNotNone(record.execution_time_ms)
        self.assertGreaterEqual(record.execution_time_ms, 0)
        self.assertEqual(record.discovered_platform_ids, ["demo_platform"])
        self.assertEqual(record.searched_platform_ids, ["demo_platform"])
        self.assertEqual(record.apartment_count, 3)
        self.assertEqual(record.new_apartment_count, 3)  # first-ever search for this location
        self.assertEqual(record.removed_apartment_count, 0)
        self.assertEqual(record.changed_apartment_count, 0)
        self.assertEqual(record.report_path, str(result.report_path))
        self.assertEqual(observed_ids, {a.id for a in result.apartments})

    def test_a_broken_platform_is_recorded_as_a_connector_failure(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="broken_platform",
                    name="Broken Platform",
                    country="Nowhere",
                    homepage="does-not-matter",
                    connector_available=True,
                    connector_name="does_not_exist_module",
                    created_at=datetime.now(timezone.utc),
                ),
            )

        request = SearchRequest(location="Example City")
        self.agent.run(request)

        with self.db.transaction() as conn:
            record = search_repository.get_search_request(conn, request.id)

        self.assertIn("broken_platform", record.discovered_platform_ids)
        self.assertNotIn("broken_platform", record.searched_platform_ids)
        self.assertEqual(record.runtime_stats["failed_platform_ids"], ["broken_platform"])
        self.assertTrue(any("broken_platform" in error for error in record.runtime_stats["errors"]))

    def test_second_run_for_the_same_location_is_a_reproducible_comparison(self) -> None:
        first_request = SearchRequest(location="Example City")
        self.agent.run(first_request)

        second_request = SearchRequest(location="Example City")
        self.agent.run(second_request)

        with self.db.transaction() as conn:
            second_record = search_repository.get_search_request(conn, second_request.id)
            comparison = search_memory_service.compare_searches(conn, first_request.id, second_request.id)

        # same fixture, same 3 listings both times — nothing changed the second run
        self.assertEqual(second_record.new_apartment_count, 0)
        self.assertEqual(second_record.removed_apartment_count, 0)
        self.assertEqual(second_record.changed_apartment_count, 0)
        self.assertEqual(comparison.previous_search_id, first_request.id)
        self.assertEqual(comparison.current_search_id, second_request.id)
        self.assertEqual(comparison.new_apartment_ids, [])
        self.assertEqual(comparison.removed_apartment_ids, [])
        self.assertEqual(comparison.changed_apartment_ids, [])

    def test_latest_search_reflects_the_most_recent_run(self) -> None:
        first_request = SearchRequest(location="Example City")
        self.agent.run(first_request)
        second_request = SearchRequest(location="Example City")
        self.agent.run(second_request)

        with self.db.transaction() as conn:
            latest = search_memory_service.latest_search(conn, "Example City")

        self.assertEqual(latest.id, second_request.id)


if __name__ == "__main__":
    unittest.main()
