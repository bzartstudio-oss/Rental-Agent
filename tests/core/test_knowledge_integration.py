"""v2.0 Step 4 integration test: RentalResearchAgent.run() must automatically record a
Knowledge Engine observation for every platform it attempts, success or failure, and
keep that platform's rollup columns current — exercised through the real orchestrator
and the real demo_platform connector, the same way tests/core/test_agent.py and
tests/core/test_search_memory_integration.py prove the rest of the pipeline.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.knowledge import knowledge_service
from src.search.search_request import SearchRequest
from src.storage import platform_intelligence_repository
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors


class KnowledgeIntegrationTests(unittest.TestCase):
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

    def test_run_records_a_successful_observation_and_updates_rollups(self) -> None:
        request = SearchRequest(location="Example City")
        self.agent.run(request)

        with self.db.transaction() as conn:
            observations = platform_intelligence_repository.get_all_observations(conn, "demo_platform")
            platform = platform_registry.get_platform(conn, "demo_platform")

        self.assertEqual(len(observations), 1)
        self.assertFalse(observations[0].failed)
        self.assertEqual(observations[0].results_count, 3)
        self.assertEqual(observations[0].search_id, request.id)
        self.assertIsNotNone(observations[0].extraction_quality_score)
        self.assertEqual(platform.success_rate, 1.0)
        self.assertIsNotNone(platform.reliability_score)

    def test_repeated_runs_accumulate_observations_without_overwriting(self) -> None:
        self.agent.run(SearchRequest(location="Example City"))
        self.agent.run(SearchRequest(location="Example City"))

        with self.db.transaction() as conn:
            observations = platform_intelligence_repository.get_all_observations(conn, "demo_platform")

        self.assertEqual(len(observations), 2)

    def test_a_broken_connector_still_gets_a_failed_observation(self) -> None:
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

        self.agent.run(SearchRequest(location="Example City"))

        with self.db.transaction() as conn:
            observations = platform_intelligence_repository.get_all_observations(conn, "broken_platform")
            platform = platform_registry.get_platform(conn, "broken_platform")

        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0].failed)
        self.assertFalse(observations[0].parsing_success)
        self.assertEqual(observations[0].results_count, 0)
        self.assertIsNone(observations[0].extraction_quality_score)
        self.assertEqual(platform.success_rate, 0.0)

    def test_knowledge_summary_reflects_the_real_run(self) -> None:
        request = SearchRequest(location="Example City")
        self.agent.run(request)

        with self.db.transaction() as conn:
            summary = knowledge_service.knowledge_summary(conn)
            best = knowledge_service.best_platforms(conn, location="Example City")

        self.assertEqual(summary.total_observations, 1)
        self.assertEqual(best[0].platform_id, "demo_platform")


if __name__ == "__main__":
    unittest.main()
