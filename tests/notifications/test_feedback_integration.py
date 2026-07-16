"""`feedback_integration.record_user_reaction()` — "Do not infer preference
merely because a notification was delivered" (the mission's own words): only
an explicit, named reaction becomes feedback evidence.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.feedback import FeedbackEngine
from src.feedback.event_types import FeedbackEventType
from src.monitoring.models import MonitoringEventType
from src.notifications import NotificationEngine, feedback_integration, service
from src.notifications.exceptions import NotificationValidationError
from src.storage.database import Database
from tests.notifications import helpers

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


class FeedbackIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.saved_search = helpers.make_saved_search(self.db, profile_id="profile-1")
        with self.db.transaction() as conn:
            self.run = helpers.make_run(conn, self.saved_search)
            self.apartment = helpers.make_apartment(conn)
        self.engine = NotificationEngine()
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)
        self.engine.process_pending_deliveries(self.db, now=_NOW)
        with self.db.transaction() as conn:
            self.delivery_id = service.get_deliveries_for_profile(conn, "profile-1")[0].delivery_id

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_a_saved_reaction_records_a_feedback_event_linked_to_the_apartment(self) -> None:
        feedback_engine = FeedbackEngine()
        with self.db.transaction() as conn:
            event = feedback_integration.record_user_reaction(conn, feedback_engine, "profile-1", self.delivery_id, "saved", _NOW + timedelta(minutes=5))
        self.assertEqual(event.event_type, FeedbackEventType.SAVED)
        self.assertEqual(event.apartment_id, self.apartment.id)
        self.assertEqual(event.source, "notification")
        self.assertEqual(event.metadata["delivery_id"], self.delivery_id)

    def test_notification_opened_and_dismissed_reactions_map_to_the_right_event_types(self) -> None:
        feedback_engine = FeedbackEngine()
        with self.db.transaction() as conn:
            opened = feedback_integration.record_user_reaction(conn, feedback_engine, "profile-1", self.delivery_id, "notification_opened", _NOW)
        self.assertEqual(opened.event_type, FeedbackEventType.NOTIFICATION_OPENED)

        with self.db.transaction() as conn:
            dismissed = feedback_integration.record_user_reaction(conn, feedback_engine, "profile-1", self.delivery_id, "dismissed", _NOW)
        self.assertEqual(dismissed.event_type, FeedbackEventType.NOTIFICATION_DISMISSED)

    def test_unknown_reaction_raises(self) -> None:
        feedback_engine = FeedbackEngine()
        with self.db.transaction() as conn:
            with self.assertRaises(NotificationValidationError):
                feedback_integration.record_user_reaction(conn, feedback_engine, "profile-1", self.delivery_id, "not_a_real_reaction", _NOW)

    def test_unknown_delivery_raises(self) -> None:
        feedback_engine = FeedbackEngine()
        with self.db.transaction() as conn:
            with self.assertRaises(NotificationValidationError):
                feedback_integration.record_user_reaction(conn, feedback_engine, "profile-1", "does-not-exist", "saved", _NOW)

    def test_a_delivery_existing_alone_never_creates_feedback_evidence(self) -> None:
        """Delivering a notification must not, by itself, produce any
        feedback event — only a real reaction does.
        """
        from src.feedback import service as feedback_service

        with self.db.transaction() as conn:
            events_before = feedback_service.get_events_for_profile(conn, "profile-1")
        self.assertEqual(events_before, [])


if __name__ == "__main__":
    unittest.main()
