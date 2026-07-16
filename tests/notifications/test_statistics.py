"""`statistics.compute_statistics()` — derived read-only from a batch's
already-persisted deliveries/attempts, computed outside `NotificationEngine`.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.monitoring.models import MonitoringEventType
from src.notifications import NotificationEngine, service, statistics
from src.notifications.registry import NotificationChannelRegistry
from src.storage.database import Database
from tests.notifications import helpers
from tests.notifications.test_engine import _AlwaysFailsChannel

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


class StatisticsTests(unittest.TestCase):
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

    def test_statistics_count_a_successful_delivery(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        batch = self.engine.process_pending_deliveries(self.db, now=_NOW)
        with self.db.transaction() as conn:
            stats = statistics.compute_statistics(conn, batch.batch_id, now=_NOW)

        self.assertEqual(stats.deliveries_by_status.get("delivered"), 1)
        self.assertEqual(stats.channel_success_counts.get("console"), 1)

    def test_statistics_count_a_failure(self) -> None:
        fake_channel = _AlwaysFailsChannel()
        NotificationChannelRegistry.register(fake_channel)
        try:
            self.engine.create_preference(
                self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["always_fails_test_channel"],
                immediate_event_types=[MonitoringEventType.NEW_MATCH],
            )
            with self.db.transaction() as conn:
                helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

            batch = self.engine.process_pending_deliveries(self.db, now=_NOW)
            with self.db.transaction() as conn:
                stats = statistics.compute_statistics(conn, batch.batch_id, now=_NOW)

            self.assertEqual(stats.channel_failure_counts.get("always_fails_test_channel"), 1)
        finally:
            NotificationChannelRegistry._channels.pop("always_fails_test_channel", None)

    def test_statistics_count_suppressed_and_quiet_hours_deferred(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH], quiet_hours_start="00:00", quiet_hours_end="23:59", timezone_name="UTC",
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, severity="info", apartment_id=self.apartment.id)

        batch = self.engine.process_pending_deliveries(self.db, now=_NOW)
        with self.db.transaction() as conn:
            stats = statistics.compute_statistics(conn, batch.batch_id, now=_NOW)

        self.assertEqual(stats.suppressed_count, 1)
        self.assertEqual(stats.quiet_hours_deferred_count, 1)

    def test_as_dict_is_json_serializable_shaped(self) -> None:
        batch = self.engine.process_pending_deliveries(self.db, now=_NOW)
        with self.db.transaction() as conn:
            stats = statistics.compute_statistics(conn, batch.batch_id, now=_NOW)
        as_dict = stats.as_dict()
        self.assertEqual(as_dict["batch_id"], batch.batch_id)
        self.assertIsInstance(as_dict["computed_at"], str)


if __name__ == "__main__":
    unittest.main()
