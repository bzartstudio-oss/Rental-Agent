"""Tests for `src/monitoring/feedback_integration.py` — "Do not infer user
preference merely because an event was generated" (the mission's own words):
a `MonitoringEvent` existing must produce zero feedback events on its own;
only an explicit call to `record_user_reaction()` does.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.feedback import FeedbackEngine
from src.monitoring import feedback_integration, service as monitoring_service
from src.monitoring.exceptions import MonitoringValidationError
from src.monitoring.models import MonitoringEvent
from src.storage import apartment_repository, monitoring_repository
from src.storage.database import Database
from src.storage.models import Apartment, MonitoringRunRecord, Platform, SavedSearchRecord

_NOW = datetime.now(timezone.utc)


class FeedbackIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, Platform(
                id="p1", name="Platform 1", country="Spain", homepage="https://p1.example", connector_available=True,
                connector_name="p1", created_at=_NOW,
            ))
            apartment_repository.insert_apartment(conn, Apartment(
                id="apt1", platform_id="p1", platform_listing_id="apt1", title="Test Apartment",
                url="https://p1.example/apt1", current_price=1000.0, current_status="available",
                first_seen_at=_NOW, last_seen_at=_NOW,
            ))
            monitoring_repository.add_saved_search(conn, SavedSearchRecord(saved_search_id="s1", name="Test", current_version=1, enabled=True, created_at=_NOW, updated_at=_NOW))
            monitoring_repository.add_run(conn, MonitoringRunRecord(monitoring_run_id="r1", saved_search_id="s1", saved_search_version=1, status="running", started_at=_NOW, platforms_attempted=[], platforms_succeeded=[], platforms_failed=[]))
            monitoring_service.record_event(conn, MonitoringEvent(
                saved_search_id="s1", saved_search_version=1, monitoring_run_id="r1", event_type="new_match",
                severity="info", significance=0.6, explanation="x", evidence={}, detected_at=_NOW, dedup_key="dk1",
                apartment_id="apt1", event_id="e1",
            ))

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_event_generation_alone_creates_no_feedback_events(self) -> None:
        """The event was already recorded in setUp — confirm nothing in the
        feedback tables exists as a side effect of that alone.
        """
        with self.db.transaction() as conn:
            from src.feedback import service as feedback_service
            events = feedback_service.get_events_for_apartment(conn, "apt1")
        self.assertEqual(events, [])

    def test_explicit_reaction_records_one_feedback_event(self) -> None:
        engine = FeedbackEngine()
        with self.db.transaction() as conn:
            feedback_event = feedback_integration.record_user_reaction(conn, engine, "profile-1", "e1", "saved", _NOW)
        self.assertEqual(feedback_event.event_type, "saved")
        self.assertEqual(feedback_event.apartment_id, "apt1")

        with self.db.transaction() as conn:
            from src.feedback import service as feedback_service
            events = feedback_service.get_events_for_profile(conn, "profile-1")
        self.assertEqual(len(events), 1)

    def test_unknown_reaction_is_rejected(self) -> None:
        with self.db.transaction() as conn:
            with self.assertRaises(MonitoringValidationError):
                feedback_integration.record_user_reaction(conn, FeedbackEngine(), "profile-1", "e1", "not_a_real_reaction", _NOW)

    def test_unknown_event_id_is_rejected(self) -> None:
        with self.db.transaction() as conn:
            with self.assertRaises(MonitoringValidationError):
                feedback_integration.record_user_reaction(conn, FeedbackEngine(), "profile-1", "does-not-exist", "saved", _NOW)


if __name__ == "__main__":
    unittest.main()
