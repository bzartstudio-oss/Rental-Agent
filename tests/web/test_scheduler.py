"""Unit tests for `MonitoringScheduler` — v2.7 Milestone 2.7.3. Every test
uses a real temporary SQLite database (never the real project one) and the
real `demo_platform` connector (a real local-fixture Playwright fetch, the
same discipline `tests/monitoring/test_engine.py` already established) —
nothing here makes a real network call.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.discovery import platform_registry
from src.monitoring import service as monitoring_service
from src.monitoring.engine import MonitoringEngine
from src.monitoring.models import MonitoringPolicy
from src.notifications.engine import NotificationEngine
from src.storage.database import Database
from src.storage.models import Platform
from src.web.scheduler import MonitoringScheduler
from tests.support import isolated_collectors

_NOW = datetime.now(timezone.utc)


class SchedulerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, Platform(
                id="demo_platform", name="Demo Platform", country="N/A (local fixture)", homepage="local-fixture",
                connector_available=True, connector_name="demo_platform", created_at=_NOW,
            ))

        self.engine = MonitoringEngine()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def _create_due_saved_search(self, name: str = "Example City Apartments"):
        """A saved search whose schedule is already due *right now* — created
        with `interval_minutes=1` but backdated 5 minutes, so
        `next_run_at` (backdated_now + 1 minute) already falls in the past
        relative to the real current time, exactly like a genuinely
        past-due saved search would.
        """
        backdated_now = datetime.now(timezone.utc) - timedelta(minutes=5)
        return self.engine.create_saved_search(
            self.db, name, {"location": "Example City", "criteria": {}},
            monitoring_policy=MonitoringPolicy(interval_minutes=1), now=backdated_now,
        )


class StartStopTests(SchedulerTestCase):
    def test_start_returns_true_and_scheduler_is_running(self) -> None:
        scheduler = MonitoringScheduler(self.db, interval_seconds=60)
        try:
            started = scheduler.start()
            self.assertTrue(started)
            self.assertTrue(scheduler.is_running)
        finally:
            scheduler.stop()

    def test_start_twice_is_idempotent_and_does_not_replace_the_thread(self) -> None:
        scheduler = MonitoringScheduler(self.db, interval_seconds=60)
        try:
            self.assertTrue(scheduler.start())
            first_thread = scheduler._thread
            second_start_result = scheduler.start()

            self.assertFalse(second_start_result)  # second call is a no-op
            self.assertIs(scheduler._thread, first_thread)  # same thread, not replaced
        finally:
            scheduler.stop()

    def test_stop_shuts_down_cleanly(self) -> None:
        scheduler = MonitoringScheduler(self.db, interval_seconds=60)
        try:
            scheduler.start()
            self.assertTrue(scheduler.is_running)
        finally:
            scheduler.stop(timeout=5.0)

        self.assertFalse(scheduler.is_running)

    def test_stop_before_start_does_not_raise(self) -> None:
        scheduler = MonitoringScheduler(self.db, interval_seconds=60)
        scheduler.stop()  # must not raise
        self.assertFalse(scheduler.is_running)

    def test_stop_is_idempotent(self) -> None:
        scheduler = MonitoringScheduler(self.db, interval_seconds=60)
        scheduler.start()
        scheduler.stop()
        scheduler.stop()  # second call must not raise
        self.assertFalse(scheduler.is_running)


class ScheduledExecutionTests(SchedulerTestCase):
    def test_scheduled_monitoring_executes_successfully(self) -> None:
        saved_search = self._create_due_saved_search()
        scheduler = MonitoringScheduler(self.db, interval_seconds=0.05)

        try:
            scheduler.start()
            deadline = time.monotonic() + 5.0
            runs = []
            while time.monotonic() < deadline and not runs:
                time.sleep(0.05)
                with self.db.transaction() as conn:
                    runs = monitoring_service.get_runs_for_saved_search(conn, saved_search.saved_search_id)
        finally:
            scheduler.stop()

        self.assertEqual(len(runs), 1)
        self.assertGreaterEqual(scheduler.run_count, 1)

    def test_scheduler_does_not_run_web_requests_are_never_blocked(self) -> None:
        """`start()` must return almost immediately — the actual monitoring
        work happens on the background thread, never synchronously inline.
        """
        self._create_due_saved_search()
        scheduler = MonitoringScheduler(self.db, interval_seconds=60)

        started_at = time.monotonic()
        scheduler.start()
        elapsed = time.monotonic() - started_at

        try:
            self.assertLess(elapsed, 0.5)  # start() itself is near-instant
        finally:
            scheduler.stop()


class OverlapPreventionTests(SchedulerTestCase):
    def test_overlapping_ticks_never_execute_the_same_due_search_twice(self) -> None:
        """Five scheduler instances (simulating five concurrent ticks — the
        same shape multiple worker processes or a race between the
        scheduler and a manual "Run Now" click would take) all fire one tick
        simultaneously against the same due saved search. The claim
        (`scheduling.claim_due_run`'s atomic conditional UPDATE, unchanged by
        this milestone) must let exactly one of them actually execute it.
        """
        saved_search = self._create_due_saved_search()
        schedulers = [MonitoringScheduler(self.db, worker_id=f"worker-{i}") for i in range(5)]

        threads = [threading.Thread(target=s._tick) for s in schedulers]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        with self.db.transaction() as conn:
            runs = monitoring_service.get_runs_for_saved_search(conn, saved_search.saved_search_id)
        self.assertEqual(len(runs), 1)


class FailureResilienceTests(SchedulerTestCase):
    def test_scheduler_survives_a_monitoring_exception_and_keeps_ticking(self) -> None:
        self._create_due_saved_search()
        scheduler = MonitoringScheduler(self.db, interval_seconds=0.05)

        call_count = {"n": 0}
        real_run_due = scheduler._engine.run_due

        def _flaky_run_due(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated monitoring failure")
            return real_run_due(*args, **kwargs)

        with patch.object(scheduler._engine, "run_due", side_effect=_flaky_run_due):
            try:
                scheduler.start()
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and scheduler.run_count < 2:
                    time.sleep(0.05)
            finally:
                scheduler.stop()

        self.assertGreaterEqual(scheduler.run_count, 2)  # kept ticking past the failure
        self.assertGreaterEqual(call_count["n"], 2)


class NotificationCompatibilityTests(SchedulerTestCase):
    def test_notifications_continue_to_work_after_a_scheduled_run(self) -> None:
        """Not a claim that a scheduled run always produces a deliverable
        event (that's `MonitoringEngine`/`NotificationEngine`'s own,
        already-tested behavior) — proves this milestone didn't disturb the
        existing notification pipeline's ability to read whatever the
        scheduler's database writes produced.
        """
        saved_search = self._create_due_saved_search()
        scheduler = MonitoringScheduler(self.db, interval_seconds=0.05)

        try:
            scheduler.start()
            deadline = time.monotonic() + 5.0
            runs = []
            while time.monotonic() < deadline and not runs:
                time.sleep(0.05)
                with self.db.transaction() as conn:
                    runs = monitoring_service.get_runs_for_saved_search(conn, saved_search.saved_search_id)
        finally:
            scheduler.stop()

        self.assertEqual(len(runs), 1)

        batch = NotificationEngine().process_pending_deliveries(self.db)  # must not raise
        self.assertEqual(batch.batch_type, "immediate")


if __name__ == "__main__":
    unittest.main()
