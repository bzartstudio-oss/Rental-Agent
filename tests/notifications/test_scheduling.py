"""`scheduling.next_digest_time()`/`is_digest_due()`/`next_delivery_time()`/
`task_scheduler_command_examples()` — the scheduler interface. Nothing here
loops or sleeps; every call is one idempotent read.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.monitoring.models import MonitoringEventType
from src.notifications import NotificationEngine, scheduling, service
from src.notifications.models import NotificationPreferenceVersion
from src.storage.database import Database
from tests.notifications import helpers

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


def _version(**overrides) -> NotificationPreferenceVersion:
    fields = dict(
        preference_id="pref-1", version=1, enabled_channels=["console"], event_types=[], immediate_event_types=[],
        digest_event_types=[], timezone="UTC", include_images=True, include_original_urls=True,
        include_ranking_explanation=True, include_geo_summary=True, include_preference_explanation=True,
        include_report_links=True, language="en", format="text", metadata={}, created_at=_NOW, digest_frequency="daily",
    )
    fields.update(overrides)
    return NotificationPreferenceVersion(**fields)


class SchedulingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.saved_search = helpers.make_saved_search(self.db, profile_id="profile-1")
        with self.db.transaction() as conn:
            self.run = helpers.make_run(conn, self.saved_search)
            self.apartment = helpers.make_apartment(conn)
        self.engine = NotificationEngine()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_manual_or_none_digest_frequency_is_never_due(self) -> None:
        with self.db.transaction() as conn:
            self.assertIsNone(scheduling.next_digest_time(conn, "pref-1", _version(digest_frequency="manual"), _NOW))
            self.assertIsNone(scheduling.next_digest_time(conn, "pref-1", _version(digest_frequency=None), _NOW))

    def test_first_digest_is_due_immediately(self) -> None:
        with self.db.transaction() as conn:
            due_at = scheduling.next_digest_time(conn, "pref-does-not-exist-yet", _version(), _NOW)
        self.assertEqual(due_at, _NOW)

    def test_next_digest_time_is_computed_from_the_last_digests_period_end(self) -> None:
        preference = self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            digest_event_types=[MonitoringEventType.PRICE_DECREASED], digest_frequency="daily",
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.PRICE_DECREASED, apartment_id=self.apartment.id)
        self.engine.generate_digest(self.db, preference.preference_id, now=_NOW)

        with self.db.transaction() as conn:
            version = service.get_latest_preference_version(conn, preference.preference_id)
            due_at = scheduling.next_digest_time(conn, preference.preference_id, version, _NOW)
        self.assertEqual(due_at, _NOW + timedelta(days=1))

    def test_is_digest_due_reflects_next_digest_time(self) -> None:
        with self.db.transaction() as conn:
            self.assertTrue(scheduling.is_digest_due(conn, "brand-new-pref", _version(), _NOW))

    def test_next_delivery_time_reads_from_the_stored_delivery(self) -> None:
        preference = self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH], quiet_hours_start="00:00", quiet_hours_end="23:59", timezone_name="UTC",
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)
        self.engine.process_pending_deliveries(self.db, now=_NOW)

        with self.db.transaction() as conn:
            delivery = service.get_deliveries_for_profile(conn, "profile-1")[0]
            next_time = scheduling.next_delivery_time(conn, delivery.delivery_id)
        self.assertEqual(next_time, delivery.next_attempt_at)

    def test_next_delivery_time_for_unknown_delivery_is_none(self) -> None:
        with self.db.transaction() as conn:
            self.assertIsNone(scheduling.next_delivery_time(conn, "does-not-exist"))

    def test_task_scheduler_examples_include_cron_and_windows_and_never_execute_anything(self) -> None:
        examples = scheduling.task_scheduler_command_examples()
        self.assertIn("cron_deliver", examples)
        self.assertIn("cron_digest", examples)
        self.assertIn("windows_task_scheduler", examples)
        self.assertIn("manual_cli", examples)
        for value in examples.values():
            self.assertIsInstance(value, str)


if __name__ == "__main__":
    unittest.main()
