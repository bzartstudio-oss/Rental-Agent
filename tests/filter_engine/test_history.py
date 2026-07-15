"""Unit tests for FilterHistory — src/filter_engine/history.py + migration 0005's
`filter_execution_history` table.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.filter_engine.history import FilterHistoryEntry, get_filter_history, record_filter_execution
from src.filter_engine.statistics import compute_filter_statistics
from src.storage import search_repository
from src.storage.database import Database
from src.storage.models import SearchRequestRecord


class FilterHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(
                    id="search-1", created_at=self.now,
                    criteria_json=json.dumps({"location": "x", "criteria": {"max_price": 2000}}),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_record_and_retrieve_a_filter_execution(self) -> None:
        stats = compute_filter_statistics([], execution_time_ms=15)
        entry = FilterHistoryEntry(
            search_id="search-1", filter_set={"max_price": 2000}, total_apartments=5,
            matched_count=3, statistics=stats, recorded_at=self.now, execution_time_ms=15,
        )

        with self.db.transaction() as conn:
            record_filter_execution(conn, entry)
            history = get_filter_history(conn, "search-1")

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].search_id, "search-1")
        self.assertEqual(history[0].filter_set, {"max_price": 2000})
        self.assertEqual(history[0].total_apartments, 5)
        self.assertEqual(history[0].matched_count, 3)
        self.assertEqual(history[0].execution_time_ms, 15)
        self.assertIn("total_apartments", history[0].statistics)

    def test_no_history_for_an_unrelated_search_id(self) -> None:
        with self.db.transaction() as conn:
            history = get_filter_history(conn, "search-does-not-exist")
        self.assertEqual(history, [])

    def test_multiple_executions_accumulate_in_order(self) -> None:
        stats = compute_filter_statistics([])
        with self.db.transaction() as conn:
            for i in range(3):
                record_filter_execution(
                    conn,
                    FilterHistoryEntry(
                        search_id="search-1", filter_set={"run": i}, total_apartments=i,
                        matched_count=i, statistics=stats, recorded_at=self.now,
                    ),
                )
            history = get_filter_history(conn, "search-1")

        self.assertEqual(len(history), 3)
        self.assertEqual([h.filter_set["run"] for h in history], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
