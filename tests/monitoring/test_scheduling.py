"""Unit tests for `src/monitoring/scheduling.py` — `compute_next_run_at()`'s
manual/interval/daily/weekly branches, and the claim/release lock exposed
through the scheduling-interface functions (not the raw repository — see
tests/storage/test_monitoring_repository.py for that layer).
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.monitoring import scheduling, service
from src.monitoring.models import MonitoringPolicy, MonitoringSchedule, SavedSearch
from src.storage.database import Database


class ComputeNextRunAtTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 16, 10, 0, 0, tzinfo=timezone.utc)  # Thursday

    def test_manual_only_has_no_next_run(self) -> None:
        self.assertIsNone(scheduling.compute_next_run_at(MonitoringPolicy(manual_only=True), self.now))

    def test_no_scheduling_field_set_has_no_next_run(self) -> None:
        self.assertIsNone(scheduling.compute_next_run_at(MonitoringPolicy(), self.now))

    def test_interval_minutes(self) -> None:
        next_run = scheduling.compute_next_run_at(MonitoringPolicy(interval_minutes=30), self.now)
        self.assertEqual(next_run, self.now + timedelta(minutes=30))

    def test_daily_at_later_today(self) -> None:
        next_run = scheduling.compute_next_run_at(MonitoringPolicy(daily_at="18:00"), self.now)
        self.assertEqual(next_run, self.now.replace(hour=18, minute=0, second=0, microsecond=0))

    def test_daily_at_already_passed_rolls_to_tomorrow(self) -> None:
        next_run = scheduling.compute_next_run_at(MonitoringPolicy(daily_at="09:00"), self.now)
        expected = (self.now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        self.assertEqual(next_run, expected)

    def test_weekly_on_future_day_this_week(self) -> None:
        next_run = scheduling.compute_next_run_at(MonitoringPolicy(weekly_on="saturday:09:00"), self.now)
        self.assertEqual(next_run.weekday(), 5)  # Saturday
        self.assertGreater(next_run, self.now)

    def test_weekly_on_same_day_already_passed_rolls_to_next_week(self) -> None:
        today_name = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[self.now.weekday()]
        next_run = scheduling.compute_next_run_at(MonitoringPolicy(weekly_on=f"{today_name}:09:00"), self.now)
        expected = self.now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=7)
        self.assertEqual(next_run, expected)


class SchedulingInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            service.record_saved_search(conn, SavedSearch(saved_search_id="s1", name="Test", current_version=1, enabled=True, created_at=self.now, updated_at=self.now))
            service.record_schedule(conn, MonitoringSchedule(saved_search_id="s1", next_run_at=self.now - timedelta(minutes=1)))

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_due_saved_searches_finds_it(self) -> None:
        with self.db.transaction() as conn:
            due = scheduling.due_saved_searches(conn, self.now)
        self.assertEqual([s.saved_search_id for s in due], ["s1"])

    def test_claim_prevents_a_second_worker(self) -> None:
        with self.db.transaction() as conn:
            first = scheduling.claim_due_run(conn, "s1", "worker-a", self.now, ttl_minutes=15)
        with self.db.transaction() as conn:
            second = scheduling.claim_due_run(conn, "s1", "worker-b", self.now, ttl_minutes=15)
        self.assertTrue(first)
        self.assertFalse(second)

    def test_claimed_saved_search_is_no_longer_due(self) -> None:
        with self.db.transaction() as conn:
            scheduling.claim_due_run(conn, "s1", "worker-a", self.now, ttl_minutes=15)
            due = scheduling.due_saved_searches(conn, self.now)
        self.assertEqual(due, [])

    def test_mark_run_completed_releases_claim_and_advances_schedule(self) -> None:
        policy = MonitoringPolicy(interval_minutes=60)
        with self.db.transaction() as conn:
            scheduling.claim_due_run(conn, "s1", "worker-a", self.now, ttl_minutes=15)
            scheduling.mark_run_completed(conn, "s1", self.now, policy)
            schedule = service.get_schedule(conn, "s1")
        self.assertIsNone(schedule.claimed_by)
        self.assertEqual(schedule.last_run_status, "completed")
        self.assertEqual(schedule.next_run_at, self.now + timedelta(minutes=60))

    def test_compute_health_reports_consecutive_failures(self) -> None:
        from src.monitoring import service as monitoring_service
        from src.monitoring.models import MonitoringRun, MonitoringRunStatus

        with self.db.transaction() as conn:
            for i in range(2):
                run = MonitoringRun(
                    saved_search_id="s1", saved_search_version=1, started_at=self.now + timedelta(minutes=i),
                    status=MonitoringRunStatus.FAILED,
                )
                monitoring_service.record_run(conn, run)
            health = scheduling.compute_health(conn, "s1")
        self.assertEqual(health.consecutive_failure_count, 2)
        self.assertFalse(health.is_healthy)


if __name__ == "__main__":
    unittest.main()
