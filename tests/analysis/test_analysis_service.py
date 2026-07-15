"""Tests for src/analysis/analysis_service.py — record_analysis (write side, only
persists metrics that have a real score) and latest_analysis/analysis_history (read
side, reconstructed from persisted apartment_analysis_metrics rows).
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis import analysis_service
from src.analysis.models import AnalysisResult, AnalyzerResult, CompositeScore
from src.storage import apartment_repository
from src.storage.database import Database
from src.storage.models import Apartment


def _analyzer_result(name: str, score, **overrides) -> AnalyzerResult:
    defaults = dict(
        analyzer_name=name, apartment_id="apt-1", score=score, confidence=0.9,
        evidence=["some evidence"], warnings=[], computed_at=datetime.now(timezone.utc),
        version="1.0.0", source="test",
    )
    defaults.update(overrides)
    return AnalyzerResult(**defaults)


class AnalysisServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO platforms (id, name, country, supported_cities, rental_types, homepage, "
                "connector_available, connector_name, discovery_method, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("test_platform", "Test", "Testland", "[]", "[]", "https://example.com", 1,
                 "src.connectors.test", "manual", datetime.now(timezone.utc).isoformat()),
            )
            apartment_repository.insert_apartment(
                conn,
                Apartment(
                    id="apt-1", platform_id="test_platform", platform_listing_id="listing-1", title="A",
                    url="https://example.com/a", current_price=1000.0, current_status="available",
                    first_seen_at=datetime.now(timezone.utc), last_seen_at=datetime.now(timezone.utc),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()


class RecordAnalysisTests(AnalysisServiceTestCase):
    def test_only_persists_analyzer_results_with_a_real_score(self) -> None:
        now = datetime.now(timezone.utc)
        result = AnalysisResult(
            apartment_id="apt-1", search_id=None, computed_at=now,
            analyzer_results=[
                _analyzer_result("walking_distance", 0.8, computed_at=now),
                _analyzer_result("nearby_supermarkets", None, confidence=None, evidence=[], warnings=["no evidence"], computed_at=now),
            ],
            composite_scores=[CompositeScore(name="location_score", score=0.8, component_analyzer_names=["walking_distance"])],
        )

        with self.db.transaction() as conn:
            analysis_service.record_analysis(conn, result)

        with self.db.transaction() as conn:
            from src.storage import analysis_metrics_repository
            metrics = analysis_metrics_repository.get_metrics_for_apartment(conn, "apt-1")

        metric_names = {m.metric_name for m in metrics}
        self.assertIn("walking_distance", metric_names)
        self.assertNotIn("nearby_supermarkets", metric_names)  # no evidence -> never persisted
        self.assertIn("composite:location_score", metric_names)

    def test_records_confidence_and_evidence(self) -> None:
        now = datetime.now(timezone.utc)
        result = AnalysisResult(
            apartment_id="apt-1", search_id=None, computed_at=now,
            analyzer_results=[_analyzer_result("walking_distance", 0.8, confidence=0.95, evidence=["1.2 km"], computed_at=now)],
            composite_scores=[],
        )

        with self.db.transaction() as conn:
            analysis_service.record_analysis(conn, result)

        with self.db.transaction() as conn:
            latest = analysis_service.latest_analysis(conn, "apt-1")

        walking = latest.analyzer_result("walking_distance")
        self.assertEqual(walking.confidence, 0.95)
        self.assertEqual(walking.evidence, ["1.2 km"])


class LatestAndHistoryTests(AnalysisServiceTestCase):
    def test_latest_analysis_returns_none_when_nothing_computed(self) -> None:
        with self.db.transaction() as conn:
            self.assertIsNone(analysis_service.latest_analysis(conn, "apt-1"))

    def test_latest_analysis_reflects_the_most_recent_run(self) -> None:
        first_seen = datetime.now(timezone.utc)
        second_seen = first_seen + timedelta(days=1)

        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO search_requests (id, created_at, criteria_json) VALUES (?, ?, ?)",
                ("search-1", first_seen.isoformat(), "{}"),
            )
            conn.execute(
                "INSERT INTO search_requests (id, created_at, criteria_json) VALUES (?, ?, ?)",
                ("search-2", second_seen.isoformat(), "{}"),
            )
            analysis_service.record_analysis(
                conn,
                AnalysisResult(
                    apartment_id="apt-1", search_id="search-1", computed_at=first_seen,
                    analyzer_results=[_analyzer_result("walking_distance", 0.5, computed_at=first_seen)],
                    composite_scores=[],
                ),
            )
            analysis_service.record_analysis(
                conn,
                AnalysisResult(
                    apartment_id="apt-1", search_id="search-2", computed_at=second_seen,
                    analyzer_results=[_analyzer_result("walking_distance", 0.9, computed_at=second_seen)],
                    composite_scores=[],
                ),
            )

        with self.db.transaction() as conn:
            latest = analysis_service.latest_analysis(conn, "apt-1")

        self.assertEqual(latest.analyzer_result("walking_distance").score, 0.9)
        self.assertEqual(latest.search_id, "search-2")

    def test_analysis_history_preserves_every_past_run_oldest_first(self) -> None:
        first_seen = datetime.now(timezone.utc)
        second_seen = first_seen + timedelta(days=1)

        with self.db.transaction() as conn:
            analysis_service.record_analysis(
                conn,
                AnalysisResult(
                    apartment_id="apt-1", search_id=None, computed_at=first_seen,
                    analyzer_results=[_analyzer_result("walking_distance", 0.5, computed_at=first_seen)],
                    composite_scores=[],
                ),
            )
            analysis_service.record_analysis(
                conn,
                AnalysisResult(
                    apartment_id="apt-1", search_id=None, computed_at=second_seen,
                    analyzer_results=[_analyzer_result("walking_distance", 0.9, computed_at=second_seen)],
                    composite_scores=[],
                ),
            )

        with self.db.transaction() as conn:
            history = analysis_service.analysis_history(conn, "apt-1")

        self.assertEqual(len(history), 2)  # never overwritten — both runs preserved
        self.assertEqual(history[0].analyzer_result("walking_distance").score, 0.5)
        self.assertEqual(history[1].analyzer_result("walking_distance").score, 0.9)


if __name__ == "__main__":
    unittest.main()
