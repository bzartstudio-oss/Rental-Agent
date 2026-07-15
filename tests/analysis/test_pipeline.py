"""Tests for src/analysis/pipeline.py — AnalysisPipeline runs every registered
analyzer for one apartment and computes composite scores, isolating a broken analyzer
the same way core/agent.py isolates a broken connector.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.base_analyzer import BaseAnalyzer
from src.analysis.models import AnalysisContext, AnalyzerMetadata
from src.analysis.pipeline import AnalysisPipeline
from src.analysis.registry import AnalysisRegistry, register_analyzer
from src.storage import reference_data_repository
from src.storage.database import Database
from src.storage.models import Apartment, KnowledgeEntry


def _make_apartment(**overrides) -> Apartment:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="apt-1", platform_id="test_platform", platform_listing_id="listing-1", title="A Nice Place",
        url="https://example.com/a", current_price=1000.0, current_status="available",
        first_seen_at=now, last_seen_at=now,
    )
    defaults.update(overrides)
    return Apartment(**defaults)


class AnalysisPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _context(self, conn, location="Example City") -> AnalysisContext:
        return AnalysisContext(conn=conn, location=location, computed_at=datetime.now(timezone.utc))

    def test_runs_every_registered_analyzer(self) -> None:
        pipeline = AnalysisPipeline()
        apartment = _make_apartment()

        with self.db.transaction() as conn:
            analyzer_results, _ = pipeline.run(apartment, self._context(conn))

        names = {r.analyzer_name for r in analyzer_results}
        self.assertIn("walking_distance", names)
        self.assertIn("nearby_supermarkets", names)
        self.assertGreaterEqual(len(analyzer_results), 11)

    def test_no_evidence_by_default_scores_are_all_none(self) -> None:
        """No coordinates, no curated knowledge_entries seeded — every analyzer should
        honestly report no evidence, not a fabricated score.
        """
        pipeline = AnalysisPipeline()
        apartment = _make_apartment()

        with self.db.transaction() as conn:
            analyzer_results, composite_scores = pipeline.run(apartment, self._context(conn))

        self.assertTrue(all(r.score is None for r in analyzer_results))
        self.assertTrue(all(c.score is None for c in composite_scores))
        self.assertTrue(all(r.warnings for r in analyzer_results))

    def test_composite_scores_include_the_four_named_ones_plus_overall(self) -> None:
        pipeline = AnalysisPipeline()
        apartment = _make_apartment()

        with self.db.transaction() as conn:
            _, composite_scores = pipeline.run(apartment, self._context(conn))

        names = {c.name for c in composite_scores}
        self.assertEqual(
            names,
            {"location_score", "convenience_score", "lifestyle_score", "accessibility_score", "overall_analysis_score"},
        )

    def test_real_evidence_produces_real_scores(self) -> None:
        """Seed a curated nearby_amenities fact and apartment coordinates + a city
        center reference point — proves the analyzers compute real, correct scores
        when evidence actually exists, not just "always None" in this test suite.
        """
        apartment = _make_apartment(latitude=40.0, longitude=-3.0)
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="nearby_amenities", key="Example City:supermarket",
                    value_json=json.dumps({"count": 5}), updated_at=datetime.now(timezone.utc),
                ),
            )
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    category="city_center", key="Example City",
                    value_json=json.dumps({"latitude": 40.0, "longitude": -3.0}),
                    updated_at=datetime.now(timezone.utc),
                ),
            )

        pipeline = AnalysisPipeline()
        with self.db.transaction() as conn:
            analyzer_results, composite_scores = pipeline.run(apartment, self._context(conn))

        supermarkets = next(r for r in analyzer_results if r.analyzer_name == "nearby_supermarkets")
        walking = next(r for r in analyzer_results if r.analyzer_name == "walking_distance")

        self.assertEqual(supermarkets.score, 1.0)  # 5 known supermarkets, saturates at 5
        self.assertEqual(walking.score, 1.0)  # apartment is exactly at the reference center

        location_score = next(c for c in composite_scores if c.name == "location_score")
        self.assertIsNotNone(location_score.score)  # at least one component had evidence

    def test_a_broken_analyzer_does_not_crash_the_pipeline(self) -> None:
        @register_analyzer
        class _BrokenAnalyzer(BaseAnalyzer):
            analyzer_name = "test_pipeline_broken_analyzer"

            def metadata(self) -> AnalyzerMetadata:
                return AnalyzerMetadata(analyzer_name=self.analyzer_name, version="9.9.9", category="test", description="broken")

            def analyze(self, apartment, context):
                raise RuntimeError("deliberately broken")

        try:
            pipeline = AnalysisPipeline()
            apartment = _make_apartment()
            with self.db.transaction() as conn:
                analyzer_results, _ = pipeline.run(apartment, self._context(conn))

            broken = next(r for r in analyzer_results if r.analyzer_name == "test_pipeline_broken_analyzer")
            other_names = {r.analyzer_name for r in analyzer_results} - {"test_pipeline_broken_analyzer"}

            self.assertIsNone(broken.score)
            self.assertIn("deliberately broken", broken.warnings[0])
            self.assertEqual(broken.version, "9.9.9")
            self.assertIn("walking_distance", other_names)  # everything else still ran
        finally:
            AnalysisRegistry._analyzers.pop("test_pipeline_broken_analyzer", None)


if __name__ == "__main__":
    unittest.main()
