"""Filter Engine Integration tests — src/feedback/filter_integration.py. Confirms
repeated filter choices become real feedback events, and that recording never
mutates the criteria dict itself (never silently promotes a preference to a
required filter).
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.feedback.engine import FeedbackEngine
from src.feedback.event_types import FeedbackEventType
from src.feedback.filter_integration import record_filter_change_events, record_filter_selection_events
from src.storage.database import Database

_NOW = datetime.now(timezone.utc)


class RecordFilterSelectionEventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.engine = FeedbackEngine()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_one_event_per_criterion(self) -> None:
        criteria = {"max_price": 1500, "min_bedrooms": 1}
        with self.db.transaction() as conn:
            events = record_filter_selection_events(self.engine, conn, "u1", criteria, occurred_at=_NOW)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.event_type == FeedbackEventType.FILTER_SELECTED for e in events))

    def test_criteria_dict_itself_is_never_mutated(self) -> None:
        criteria = {"max_price": 1500}
        original = dict(criteria)
        with self.db.transaction() as conn:
            record_filter_selection_events(self.engine, conn, "u1", criteria, occurred_at=_NOW)
        self.assertEqual(criteria, original)

    def test_events_are_actually_persisted(self) -> None:
        with self.db.transaction() as conn:
            record_filter_selection_events(self.engine, conn, "u1", {"max_price": 1500}, occurred_at=_NOW)
            exported = self.engine.export_feedback_history(conn, "u1")
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0].event_value, {"key": "max_price", "value": 1500})


class RecordFilterChangeEventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.engine = FeedbackEngine()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_new_criterion_is_filter_selected(self) -> None:
        with self.db.transaction() as conn:
            events = record_filter_change_events(self.engine, conn, "u1", {}, {"max_price": 1500}, occurred_at=_NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, FeedbackEventType.FILTER_SELECTED)

    def test_removed_criterion_is_filter_removed(self) -> None:
        with self.db.transaction() as conn:
            events = record_filter_change_events(self.engine, conn, "u1", {"max_price": 1500}, {}, occurred_at=_NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, FeedbackEventType.FILTER_REMOVED)

    def test_unchanged_criterion_produces_no_event(self) -> None:
        with self.db.transaction() as conn:
            events = record_filter_change_events(
                self.engine, conn, "u1", {"max_price": 1500}, {"max_price": 1500}, occurred_at=_NOW,
            )
        self.assertEqual(events, [])

    def test_never_required_conditions_stay_explicit_user_decisions(self) -> None:
        """Recording a filter choice never mutates `new_criteria` — the actual
        hard-filter behavior lives entirely in `SearchRequest.criteria`/
        `FilterEngine`, untouched by this module.
        """
        new_criteria = {"max_price": 1500}
        with self.db.transaction() as conn:
            record_filter_change_events(self.engine, conn, "u1", {}, new_criteria, occurred_at=_NOW)
        self.assertEqual(new_criteria, {"max_price": 1500})


if __name__ == "__main__":
    unittest.main()
