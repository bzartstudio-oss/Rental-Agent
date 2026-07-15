"""Unit tests for sync_filter_definitions — src/filter_engine/sync.py + the
`filter_definitions` table (migration 0001, unused until v2.5 Step 9)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.storage import filter_definitions_repository
from src.storage.database import Database
from src.filter_engine.sync import sync_filter_definitions


class SyncFilterDefinitionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_syncs_all_39_built_in_filters(self) -> None:
        with self.db.transaction() as conn:
            count = sync_filter_definitions(conn)
            definitions = filter_definitions_repository.list_definitions(conn)

        self.assertEqual(count, 39)
        self.assertEqual(len(definitions), 39)

    def test_a_real_definition_has_the_expected_shape(self) -> None:
        with self.db.transaction() as conn:
            sync_filter_definitions(conn)
            definition = filter_definitions_repository.get_definition(conn, "max_price")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.display_name, "Maximum Price")
        self.assertEqual(definition.category, "price")
        self.assertEqual(definition.value_type, "number")

    def test_syncing_twice_does_not_duplicate_or_error(self) -> None:
        with self.db.transaction() as conn:
            sync_filter_definitions(conn)
            sync_filter_definitions(conn)  # must not raise
            definitions = filter_definitions_repository.list_definitions(conn)

        self.assertEqual(len(definitions), 39)  # still no duplicates


if __name__ == "__main__":
    unittest.main()
