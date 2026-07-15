"""Round-trip tests for storage/analysis_metrics_repository.py — the v2.0 Step 6 data
access layer for `apartment_analysis_metrics`.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.storage import analysis_metrics_repository, apartment_repository
from src.storage.database import Database
from src.storage.models import Apartment, ApartmentAnalysisMetric


class AnalysisMetricsRepositoryTests(unittest.TestCase):
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

    def _metric(self, **overrides) -> ApartmentAnalysisMetric:
        defaults = dict(
            apartment_id="apt-1", metric_name="walking_distance", metric_value=0.8,
            source_module="haversine_calculation", computed_at=datetime.now(timezone.utc),
            confidence=1.0, evidence=["1.0 km from center"], warnings=[], analyzer_version="1.0.0",
        )
        defaults.update(overrides)
        return ApartmentAnalysisMetric(**defaults)

    def test_round_trip(self) -> None:
        with self.db.transaction() as conn:
            analysis_metrics_repository.add_metric(conn, self._metric())

        with self.db.transaction() as conn:
            metrics = analysis_metrics_repository.get_metrics_for_apartment(conn, "apt-1")

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].metric_value, 0.8)
        self.assertEqual(metrics[0].confidence, 1.0)
        self.assertEqual(metrics[0].evidence, ["1.0 km from center"])
        self.assertEqual(metrics[0].analyzer_version, "1.0.0")

    def test_filters_by_metric_name(self) -> None:
        with self.db.transaction() as conn:
            analysis_metrics_repository.add_metric(conn, self._metric(metric_name="walking_distance"))
            analysis_metrics_repository.add_metric(conn, self._metric(metric_name="nearby_supermarkets"))

        with self.db.transaction() as conn:
            metrics = analysis_metrics_repository.get_metrics_for_apartment(conn, "apt-1", metric_name="walking_distance")

        self.assertEqual([m.metric_name for m in metrics], ["walking_distance"])

    def test_never_overwrites_previous_metrics(self) -> None:
        first_seen = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            analysis_metrics_repository.add_metric(conn, self._metric(metric_value=0.5, computed_at=first_seen))
            analysis_metrics_repository.add_metric(
                conn, self._metric(metric_value=0.9, computed_at=first_seen + timedelta(days=1))
            )

        with self.db.transaction() as conn:
            metrics = analysis_metrics_repository.get_metrics_for_apartment(conn, "apt-1", metric_name="walking_distance")

        self.assertEqual([m.metric_value for m in metrics], [0.5, 0.9])  # both preserved, oldest first

    def test_get_latest_metrics_for_apartment_returns_only_the_most_recent_run(self) -> None:
        first_seen = datetime.now(timezone.utc)
        second_seen = first_seen + timedelta(days=1)
        with self.db.transaction() as conn:
            analysis_metrics_repository.add_metric(
                conn, self._metric(metric_name="walking_distance", metric_value=0.5, computed_at=first_seen)
            )
            analysis_metrics_repository.add_metric(
                conn, self._metric(metric_name="nearby_supermarkets", metric_value=0.6, computed_at=first_seen)
            )
            analysis_metrics_repository.add_metric(
                conn, self._metric(metric_name="walking_distance", metric_value=0.9, computed_at=second_seen)
            )

        with self.db.transaction() as conn:
            latest = analysis_metrics_repository.get_latest_metrics_for_apartment(conn, "apt-1")

        self.assertEqual({m.metric_name: m.metric_value for m in latest}, {"walking_distance": 0.9})

    def test_get_latest_metrics_returns_empty_list_when_nothing_computed(self) -> None:
        with self.db.transaction() as conn:
            latest = analysis_metrics_repository.get_latest_metrics_for_apartment(conn, "apt-1")
        self.assertEqual(latest, [])

    def test_get_metrics_for_search(self) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO search_requests (id, created_at, criteria_json) VALUES (?, ?, ?)",
                ("search-1", datetime.now(timezone.utc).isoformat(), "{}"),
            )
            analysis_metrics_repository.add_metric(conn, self._metric(search_id="search-1"))

        with self.db.transaction() as conn:
            metrics = analysis_metrics_repository.get_metrics_for_search(conn, "search-1")

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].search_id, "search-1")


if __name__ == "__main__":
    unittest.main()
