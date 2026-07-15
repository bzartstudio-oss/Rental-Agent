"""Round-trip tests for storage/platform_intelligence_repository.py — the v2.0 Step 4
data access layer for `platform_performance_observations`.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.storage import platform_intelligence_repository
from src.storage.database import Database
from src.storage.models import Platform, PlatformPerformanceObservation


class PlatformIntelligenceRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="test_platform", name="Test", country="Testland", homepage="https://example.com",
                    connector_available=True, connector_name="test_platform",
                    created_at=datetime.now(timezone.utc),
                ),
            )
            conn.execute(
                "INSERT INTO search_requests (id, created_at, criteria_json) VALUES (?, ?, ?)",
                ("search-1", datetime.now(timezone.utc).isoformat(), "{}"),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _observation(self, search_id="search-1", failed=False, observed_at=None, **overrides) -> PlatformPerformanceObservation:
        defaults = dict(
            platform_id="test_platform", search_id=search_id, results_count=3, failed=failed,
            parsing_success=not failed, observed_at=observed_at or datetime.now(timezone.utc),
            response_time_ms=500, extraction_quality_score=0.9, image_quality_score=1.0,
            availability_quality_score=1.0, duplicate_rate=0.0, ranking_usefulness_score=1.2,
        )
        defaults.update(overrides)
        return PlatformPerformanceObservation(**defaults)

    def test_round_trip(self) -> None:
        with self.db.transaction() as conn:
            platform_intelligence_repository.add_observation(conn, self._observation())

        with self.db.transaction() as conn:
            observations = platform_intelligence_repository.get_all_observations(conn, "test_platform")

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].results_count, 3)
        self.assertFalse(observations[0].failed)
        self.assertEqual(observations[0].ranking_usefulness_score, 1.2)

    def test_failed_observation_has_null_quality_scores(self) -> None:
        failed_obs = PlatformPerformanceObservation(
            platform_id="test_platform", search_id="search-1", results_count=0, failed=True,
            parsing_success=False, observed_at=datetime.now(timezone.utc), response_time_ms=200,
        )
        with self.db.transaction() as conn:
            platform_intelligence_repository.add_observation(conn, failed_obs)

        with self.db.transaction() as conn:
            observations = platform_intelligence_repository.get_all_observations(conn, "test_platform")

        self.assertTrue(observations[0].failed)
        self.assertIsNone(observations[0].extraction_quality_score)

    def test_get_recent_observations_is_newest_first_and_respects_limit(self) -> None:
        first_seen = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            for i in range(3):
                platform_intelligence_repository.add_observation(
                    conn, self._observation(observed_at=first_seen + timedelta(minutes=i), results_count=i)
                )

        with self.db.transaction() as conn:
            recent = platform_intelligence_repository.get_recent_observations(conn, "test_platform", limit=2)

        self.assertEqual([o.results_count for o in recent], [2, 1])

    def test_get_last_observed_at_distinguishes_success_and_failure(self) -> None:
        first_seen = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            platform_intelligence_repository.add_observation(conn, self._observation(observed_at=first_seen, failed=False))
            platform_intelligence_repository.add_observation(
                conn, self._observation(observed_at=first_seen + timedelta(minutes=1), failed=True)
            )

        with self.db.transaction() as conn:
            last_success = platform_intelligence_repository.get_last_observed_at(conn, "test_platform", failed=False)
            last_failure = platform_intelligence_repository.get_last_observed_at(conn, "test_platform", failed=True)

        self.assertEqual(last_success, first_seen)
        self.assertEqual(last_failure, first_seen + timedelta(minutes=1))

    def test_get_last_observed_at_returns_none_when_no_matching_observation(self) -> None:
        with self.db.transaction() as conn:
            last_failure = platform_intelligence_repository.get_last_observed_at(conn, "test_platform", failed=True)
        self.assertIsNone(last_failure)

    def test_count_all_observations(self) -> None:
        with self.db.transaction() as conn:
            platform_intelligence_repository.add_observation(conn, self._observation())
            platform_intelligence_repository.add_observation(conn, self._observation())

        with self.db.transaction() as conn:
            total = platform_intelligence_repository.count_all_observations(conn)

        self.assertEqual(total, 2)


if __name__ == "__main__":
    unittest.main()
