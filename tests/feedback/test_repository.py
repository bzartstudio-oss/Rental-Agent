"""Migration + append-only-history tests for `storage/feedback_repository.py` +
migration 0007's four tables — real database, real round-trips.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.storage import feedback_repository
from src.storage.database import Database
from src.storage.models import (
    FeedbackEventRecord,
    PreferenceAdjustmentRecord,
    PreferenceObservationRecord,
    PreferenceSnapshotRecord,
)

_NOW = datetime.now(timezone.utc)


class MigrationTests(unittest.TestCase):
    def test_all_four_tables_exist_after_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Database(db_path=Path(tmp_dir) / "test.db")
            with db.transaction() as conn:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in ("feedback_events", "preference_observations", "preference_adjustments", "preference_snapshots"):
                self.assertIn(table, tables)


class FeedbackEventRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_add_and_retrieve_an_event(self) -> None:
        with self.db.transaction() as conn:
            feedback_repository.add_event(
                conn, FeedbackEventRecord(event_id="e1", profile_id="u1", event_type="saved",
                                           event_value={"x": 1}, occurred_at=_NOW, source="cli", metadata={}),
            )
            events = feedback_repository.get_events_for_profile(conn, "u1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "e1")
        self.assertEqual(events[0].event_value, {"x": 1})

    def test_get_by_apartment(self) -> None:
        with self.db.transaction() as conn:
            feedback_repository.add_event(
                conn, FeedbackEventRecord(event_id="e1", profile_id="u1", event_type="saved",
                                           event_value={}, occurred_at=_NOW, source="cli", metadata={}, apartment_id="apt-1"),
            )
            events = feedback_repository.get_events_for_apartment(conn, "apt-1")
        self.assertEqual(len(events), 1)

    def test_events_persist_in_insertion_order_never_overwritten(self) -> None:
        """No `update_event`/`delete_event` function exists — the only way to
        change history is to add a new row.
        """
        self.assertFalse(hasattr(feedback_repository, "update_event"))
        self.assertFalse(hasattr(feedback_repository, "delete_event"))

        with self.db.transaction() as conn:
            for i in range(3):
                feedback_repository.add_event(
                    conn, FeedbackEventRecord(event_id=f"e{i}", profile_id="u1", event_type="viewed",
                                               event_value={"i": i}, occurred_at=_NOW, source="cli", metadata={}),
                )
            events = feedback_repository.get_events_for_profile(conn, "u1")
        self.assertEqual(len(events), 3)
        self.assertEqual([e.event_id for e in events], ["e0", "e1", "e2"])


class PreferenceObservationRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            feedback_repository.add_event(
                conn, FeedbackEventRecord(event_id="e1", profile_id="u1", event_type="saved",
                                           event_value={}, occurred_at=_NOW, source="cli", metadata={}),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_add_and_retrieve_observations(self) -> None:
        with self.db.transaction() as conn:
            feedback_repository.add_observation(
                conn, PreferenceObservationRecord(profile_id="u1", preference_key="price_sensitivity", event_id="e1",
                                                   direction="supporting", magnitude=0.8, source_type="inferred",
                                                   computed_at=_NOW, explanation="x"),
            )
            observations = feedback_repository.get_observations(conn, "u1", "price_sensitivity")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].magnitude, 0.8)


class PreferenceAdjustmentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_add_and_retrieve_adjustments_in_order(self) -> None:
        with self.db.transaction() as conn:
            for i in range(3):
                feedback_repository.add_adjustment(
                    conn, PreferenceAdjustmentRecord(profile_id="u1", preference_key="price_sensitivity",
                                                      reason=f"r{i}", triggered_by_event_ids=[], adjustment_type="inferred",
                                                      applied_at=_NOW, new_value={"importance": i / 10}),
                )
            adjustments = feedback_repository.get_adjustments(conn, "u1", "price_sensitivity")
        self.assertEqual(len(adjustments), 3)
        self.assertEqual([a.reason for a in adjustments], ["r0", "r1", "r2"])

    def test_get_by_id(self) -> None:
        with self.db.transaction() as conn:
            new_id = feedback_repository.add_adjustment(
                conn, PreferenceAdjustmentRecord(profile_id="u1", preference_key="x", reason="r",
                                                  triggered_by_event_ids=[], adjustment_type="inferred", applied_at=_NOW),
            )
            fetched = feedback_repository.get_adjustment_by_id(conn, new_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.reason, "r")

    def test_reverses_adjustment_id_round_trips(self) -> None:
        with self.db.transaction() as conn:
            original_id = feedback_repository.add_adjustment(
                conn, PreferenceAdjustmentRecord(profile_id="u1", preference_key="x", reason="original",
                                                  triggered_by_event_ids=[], adjustment_type="inferred", applied_at=_NOW),
            )
            feedback_repository.add_adjustment(
                conn, PreferenceAdjustmentRecord(profile_id="u1", preference_key="x", reason="undo",
                                                  triggered_by_event_ids=[], adjustment_type="undo", applied_at=_NOW,
                                                  reverses_adjustment_id=original_id),
            )
            adjustments = feedback_repository.get_adjustments(conn, "u1", "x")
        self.assertEqual(adjustments[-1].reverses_adjustment_id, original_id)


class PreferenceSnapshotRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_add_and_retrieve_snapshots(self) -> None:
        with self.db.transaction() as conn:
            feedback_repository.add_snapshot(
                conn, PreferenceSnapshotRecord(profile_id="u1", snapshot={"a": 1}, reason="auto", created_at=_NOW),
            )
            snapshots = feedback_repository.get_snapshots(conn, "u1")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].snapshot, {"a": 1})


if __name__ == "__main__":
    unittest.main()
