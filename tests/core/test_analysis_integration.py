"""v2.0 Step 6 integration test: RentalResearchAgent.run() must automatically analyze
every apartment it collects and pass the results through to the report — exercised
through the real orchestrator and the real demo_platform connector, the same way
tests/core/test_knowledge_integration.py and test_search_memory_integration.py prove
the rest of the pipeline.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.search.search_request import SearchRequest
from src.storage import analysis_metrics_repository, apartment_repository, reference_data_repository
from src.storage.database import Database
from src.storage.models import KnowledgeEntry, Platform
from tests.support import isolated_collectors


class AnalysisIntegrationTests(unittest.TestCase):
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

    def test_run_analyzes_every_apartment_and_shows_it_in_the_report(self) -> None:
        request = SearchRequest(location="Example City")
        result = self.agent.run(request)

        report_content = result.report_path.read_text(encoding="utf-8")
        self.assertIn('class="analysis"', report_content)
        self.assertIn("walking_distance", report_content)

    def test_apartment_data_is_never_mutated_by_analysis(self) -> None:
        request = SearchRequest(location="Example City")
        result = self.agent.run(request)

        with self.db.transaction() as conn:
            for apartment in result.apartments:
                fetched = apartment_repository.get_apartment(conn, apartment.id)
                self.assertEqual(fetched.title, apartment.title)
                self.assertEqual(fetched.current_price, apartment.current_price)

    def test_no_evidence_by_default_means_nothing_is_persisted(self) -> None:
        """No curated knowledge_entries for "Example City" — even though the demo
        fixture's apartments carry real coordinates (v2.6 Milestone 2.6.2), the
        walking_distance/public_transport analyzers also need a curated
        `city_center`/`public_transport` reference point for the search location,
        which nothing seeds automatically. Every analyzer should honestly report no
        evidence, and nothing gets written to apartment_analysis_metrics (see
        src/analysis/analysis_service.py).
        """
        request = SearchRequest(location="Example City")
        result = self.agent.run(request)

        with self.db.transaction() as conn:
            for apartment in result.apartments:
                metrics = analysis_metrics_repository.get_metrics_for_apartment(conn, apartment.id)
                self.assertEqual(metrics, [])

    def test_seeded_curated_data_produces_real_persisted_scores(self) -> None:
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="nearby_amenities", key="Example City:supermarket",
                    value_json=json.dumps({"count": 5}), updated_at=datetime.now(timezone.utc),
                ),
            )

        request = SearchRequest(location="Example City")
        result = self.agent.run(request)

        with self.db.transaction() as conn:
            for apartment in result.apartments:
                metrics = analysis_metrics_repository.get_metrics_for_apartment(
                    conn, apartment.id, metric_name="nearby_supermarkets"
                )
                self.assertEqual(len(metrics), 1)
                self.assertEqual(metrics[0].metric_value, 1.0)
                self.assertEqual(metrics[0].search_id, request.id)


if __name__ == "__main__":
    unittest.main()
