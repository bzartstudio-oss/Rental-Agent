"""Unit tests for `src.connectors.rentcast.budget` — v2.7 Milestone 2.7.2.
Every test uses a real temporary SQLite database (never the real project
one) and makes no network call of any kind.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.connectors.rentcast import budget
from src.storage.database import Database


class CallBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_call_is_granted_when_budget_available(self) -> None:
        now = datetime(2026, 7, 18, tzinfo=timezone.utc)
        with self.db.transaction() as conn:
            granted = budget.try_consume_call(conn, "rentcast", monthly_limit=50, now=now)

        self.assertTrue(granted)
        with self.db.transaction() as conn:
            count, limit = budget.current_usage(conn, "rentcast", now)
        self.assertEqual(count, 1)
        self.assertEqual(limit, 50)

    def test_call_is_denied_once_budget_is_exhausted(self) -> None:
        now = datetime(2026, 7, 18, tzinfo=timezone.utc)
        for _ in range(3):
            with self.db.transaction() as conn:
                self.assertTrue(budget.try_consume_call(conn, "rentcast", monthly_limit=3, now=now))

        with self.db.transaction() as conn:
            granted = budget.try_consume_call(conn, "rentcast", monthly_limit=3, now=now)

        self.assertFalse(granted)
        with self.db.transaction() as conn:
            count, limit = budget.current_usage(conn, "rentcast", now)
        self.assertEqual(count, 3)  # the denied attempt must not have incremented it
        self.assertEqual(limit, 3)

    def test_current_usage_is_zero_zero_before_any_call(self) -> None:
        now = datetime(2026, 7, 18, tzinfo=timezone.utc)
        with self.db.transaction() as conn:
            count, limit = budget.current_usage(conn, "rentcast", now)
        self.assertEqual((count, limit), (0, 0))

    def test_budget_resets_automatically_at_the_start_of_a_new_month(self) -> None:
        july = datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)
        august = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)

        with self.db.transaction() as conn:
            for _ in range(3):
                self.assertTrue(budget.try_consume_call(conn, "rentcast", monthly_limit=3, now=july))
            self.assertFalse(budget.try_consume_call(conn, "rentcast", monthly_limit=3, now=july))

        # A new calendar month starts a fresh budget with no explicit reset step.
        with self.db.transaction() as conn:
            granted = budget.try_consume_call(conn, "rentcast", monthly_limit=3, now=august)

        self.assertTrue(granted)
        with self.db.transaction() as conn:
            july_count, _ = budget.current_usage(conn, "rentcast", july)
            august_count, _ = budget.current_usage(conn, "rentcast", august)
        self.assertEqual(july_count, 3)  # last month's usage is preserved as history
        self.assertEqual(august_count, 1)

    def test_different_providers_have_independent_budgets(self) -> None:
        now = datetime(2026, 7, 18, tzinfo=timezone.utc)
        with self.db.transaction() as conn:
            for _ in range(2):
                self.assertTrue(budget.try_consume_call(conn, "rentcast", monthly_limit=2, now=now))
            self.assertFalse(budget.try_consume_call(conn, "rentcast", monthly_limit=2, now=now))
            # A different provider_id must not be affected by rentcast's exhaustion.
            self.assertTrue(budget.try_consume_call(conn, "some_other_provider", monthly_limit=2, now=now))

    def test_concurrent_calls_never_exceed_the_budget(self) -> None:
        """20 threads race for a budget of 5 — SQLite's single-writer file
        lock, combined with the atomic conditional UPDATE, must guarantee
        exactly 5 successes regardless of scheduling. Each thread opens its
        own connection via its own `self.db.transaction()` call, the same
        way two separate worker processes would.
        """
        now = datetime(2026, 7, 18, tzinfo=timezone.utc)
        results: list[bool] = []
        lock = threading.Lock()

        def attempt() -> None:
            with self.db.transaction() as conn:
                granted = budget.try_consume_call(conn, "rentcast", monthly_limit=5, now=now)
            with lock:
                results.append(granted)

        threads = [threading.Thread(target=attempt) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(len(results), 20)
        self.assertEqual(sum(1 for granted in results if granted), 5)
        with self.db.transaction() as conn:
            count, limit = budget.current_usage(conn, "rentcast", now)
        self.assertEqual(count, 5)
        self.assertEqual(limit, 5)


if __name__ == "__main__":
    unittest.main()
