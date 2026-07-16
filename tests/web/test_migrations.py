"""Migration tests for 0011_web_dashboard.sql — see docs/32_Web_Dashboard.md
"Database". Mirrors `tests/storage/test_database_migrations.py`'s own shape.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.storage.database import Database


class Migration0011WebDashboardTablesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_every_web_table_exists(self) -> None:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'web_%'"
            ).fetchall()
        tables = {row["name"] for row in rows}
        self.assertEqual(
            tables, {"web_jobs", "web_ui_preferences", "web_saved_comparisons", "web_recent_views"}
        )

    def test_key_indexes_exist(self) -> None:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND sql LIKE '%web_%'"
            ).fetchall()
        index_names = {row["name"] for row in rows}
        for expected in (
            "idx_web_jobs_status_created", "idx_web_jobs_profile",
            "idx_web_saved_comparisons_profile", "idx_web_recent_views_profile_viewed",
        ):
            self.assertIn(expected, index_names)

    def test_applying_migrations_twice_does_not_error(self) -> None:
        Database(db_path=self.db.db_path)  # re-runs _apply_migrations(), already-applied versions skipped
        with self.db.transaction() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM web_jobs").fetchone()["c"]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
