"""Integration tests for `NotificationEngine` — the mission's own explicit
verification checklist: a channel failure never deletes the underlying
`MonitoringEvent`, one channel's failure doesn't block another succeeding,
quiet hours defer non-critical events, rate-limited events are suppressed
(never silently dropped), retries are idempotent, and digests group/summarize
correctly.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.monitoring import service as monitoring_service
from src.monitoring.models import MonitoringEventType
from src.notifications import NotificationEngine, service
from src.notifications.channels.console_channel import ConsoleNotificationChannel
from src.notifications.exceptions import NotificationValidationError
from src.notifications.models import NotificationDeliveryStatus
from src.notifications.registry import NotificationChannelRegistry
from src.storage.database import Database
from tests.notifications import helpers

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


class _AlwaysFailsChannel(ConsoleNotificationChannel):
    """A test-only channel that always fails, used to prove one channel's
    failure never blocks another channel's success — never registered under
    "console"/"file"/etc., always its own distinct name.
    """

    channel_name = "always_fails_test_channel"

    def send(self, message):
        from src.notifications.models import NotificationChannelResult

        return NotificationChannelResult(channel=self.channel_name, success=False, error="simulated failure", error_category="server_error")


class NotificationEngineImmediateDeliveryTests(unittest.TestCase):
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

    def test_an_eligible_immediate_event_is_delivered_via_console(self) -> None:
        preference = self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        batch = self.engine.process_pending_deliveries(self.db, now=_NOW)
        self.assertEqual(batch.deliveries_succeeded, 1)

        with self.db.transaction() as conn:
            deliveries = service.get_deliveries_for_profile(conn, "profile-1")
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].status, NotificationDeliveryStatus.DELIVERED)

    def test_original_monitoring_events_are_never_modified_by_delivery(self) -> None:
        preference = self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)

        with self.db.transaction() as conn:
            stored_event = monitoring_service.get_event(conn, event.event_id)
        self.assertFalse(stored_event.acknowledged)  # untouched by delivery
        self.assertEqual(stored_event.explanation, event.explanation)

    def test_a_second_delivery_run_does_not_duplicate_an_already_delivered_event(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)
        self.engine.process_pending_deliveries(self.db, now=_NOW + timedelta(minutes=1))  # re-run

        with self.db.transaction() as conn:
            deliveries = service.get_deliveries_for_profile(conn, "profile-1")
        self.assertEqual(len(deliveries), 1)  # idempotent — not delivered twice

    def test_ineligible_event_produces_no_delivery(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH], minimum_significance=0.9,
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, significance=0.1, apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)
        with self.db.transaction() as conn:
            deliveries = service.get_deliveries_for_profile(conn, "profile-1")
        self.assertEqual(deliveries, [])

    def test_a_profile_level_preference_applies_to_every_saved_search_for_that_profile(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=None, enabled_channels=["console"],  # profile-level, not saved-search-scoped
            immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        batch = self.engine.process_pending_deliveries(self.db, now=_NOW)
        self.assertEqual(batch.deliveries_succeeded, 1)


class NotificationEngineFailureIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.saved_search = helpers.make_saved_search(self.db, profile_id="profile-1")
        with self.db.transaction() as conn:
            self.run = helpers.make_run(conn, self.saved_search)
            self.apartment = helpers.make_apartment(conn)
        self.engine = NotificationEngine()

        self._fake_channel = _AlwaysFailsChannel()
        NotificationChannelRegistry.register(self._fake_channel)

    def tearDown(self) -> None:
        NotificationChannelRegistry._channels.pop("always_fails_test_channel", None)
        self._tmp_dir.cleanup()

    def test_one_channel_failing_does_not_prevent_another_channel_from_succeeding(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id,
            enabled_channels=["console", "always_fails_test_channel"], immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)

        with self.db.transaction() as conn:
            deliveries = service.get_deliveries_for_profile(conn, "profile-1")
            attempts = service.get_attempts_for_delivery(conn, deliveries[0].delivery_id)

        self.assertEqual(deliveries[0].status, NotificationDeliveryStatus.PARTIALLY_DELIVERED)
        statuses_by_channel = {a.channel: a.status for a in attempts}
        self.assertEqual(statuses_by_channel["console"], "delivered")
        self.assertEqual(statuses_by_channel["always_fails_test_channel"], "failed")

    def test_a_failed_delivery_is_scheduled_for_retry_not_lost(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id,
            enabled_channels=["always_fails_test_channel"], immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)

        with self.db.transaction() as conn:
            deliveries = service.get_deliveries_for_profile(conn, "profile-1")
        self.assertEqual(deliveries[0].status, NotificationDeliveryStatus.RETRY_SCHEDULED)
        self.assertIsNotNone(deliveries[0].next_attempt_at)

    def test_retrying_is_idempotent_and_only_reattempts_channels_not_yet_delivered(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id,
            enabled_channels=["console", "always_fails_test_channel"], immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)
        with self.db.transaction() as conn:
            delivery_before = service.get_deliveries_for_profile(conn, "profile-1")[0]

        later = _NOW + timedelta(minutes=1)
        batch = self.engine.retry_due_failures(self.db, now=later)
        self.assertEqual(batch.deliveries_attempted, 1)

        with self.db.transaction() as conn:
            deliveries = service.get_deliveries_for_profile(conn, "profile-1")
            attempts = service.get_attempts_for_delivery(conn, delivery_before.delivery_id)

        self.assertEqual(len(deliveries), 1)  # still exactly one logical delivery — never duplicated
        console_attempts = [a for a in attempts if a.channel == "console"]
        self.assertEqual(len(console_attempts), 1)  # console already succeeded — never re-sent
        failing_attempts = [a for a in attempts if a.channel == "always_fails_test_channel"]
        self.assertEqual(len(failing_attempts), 2)  # only the still-failing channel was retried

    def test_repeated_retries_eventually_dead_letter_to_failed(self) -> None:
        from src.notifications.models import NotificationConfiguration, NotificationPolicy

        engine = NotificationEngine(NotificationConfiguration(default_policy=NotificationPolicy(dead_letter_after_attempts=2)))
        engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id,
            enabled_channels=["always_fails_test_channel"], immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        engine.process_pending_deliveries(self.db, now=_NOW)
        engine.retry_due_failures(self.db, now=_NOW + timedelta(minutes=1))

        with self.db.transaction() as conn:
            delivery = service.get_deliveries_for_profile(conn, "profile-1")[0]
        self.assertEqual(delivery.status, NotificationDeliveryStatus.FAILED)
        self.assertIsNone(delivery.next_attempt_at)


class NotificationEngineQuietHoursAndRateLimitTests(unittest.TestCase):
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

    def test_a_non_critical_event_during_quiet_hours_is_suppressed_and_deferred(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH], quiet_hours_start="00:00", quiet_hours_end="23:59", timezone_name="UTC",
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, severity="info", apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)

        with self.db.transaction() as conn:
            delivery = service.get_deliveries_for_profile(conn, "profile-1")[0]
        self.assertEqual(delivery.status, NotificationDeliveryStatus.SUPPRESSED)
        self.assertIn("quiet hours", delivery.notes.lower())
        self.assertIsNotNone(delivery.next_attempt_at)

    def test_a_critical_event_bypasses_quiet_hours(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.MONITORING_RUN_FAILED], quiet_hours_start="00:00", quiet_hours_end="23:59", timezone_name="UTC",
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.MONITORING_RUN_FAILED, severity="critical", apartment_id=None)

        self.engine.process_pending_deliveries(self.db, now=_NOW)

        with self.db.transaction() as conn:
            delivery = service.get_deliveries_for_profile(conn, "profile-1")[0]
        self.assertEqual(delivery.status, NotificationDeliveryStatus.DELIVERED)

    def test_a_rate_limited_channel_is_suppressed_with_an_explanatory_note(self) -> None:
        self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH], max_per_hour=0,
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)

        with self.db.transaction() as conn:
            delivery = service.get_deliveries_for_profile(conn, "profile-1")[0]
        self.assertEqual(delivery.status, NotificationDeliveryStatus.SUPPRESSED)
        self.assertIn("rate limit", delivery.notes.lower())


class NotificationEngineDigestTests(unittest.TestCase):
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

    def test_manual_digest_generation_groups_digest_only_events(self) -> None:
        preference = self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[], digest_event_types=[MonitoringEventType.PRICE_DECREASED], digest_frequency="daily",
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.PRICE_DECREASED, apartment_id=self.apartment.id)

        delivery = self.engine.generate_digest(self.db, preference.preference_id, now=_NOW)
        self.assertIsNotNone(delivery)
        self.assertTrue(delivery.is_digest)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.DELIVERED)

    def test_digest_membership_is_reproducible_and_no_duplicate_membership_across_digests(self) -> None:
        preference = self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[], digest_event_types=[MonitoringEventType.PRICE_DECREASED], digest_frequency="daily",
        )
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.PRICE_DECREASED, apartment_id=self.apartment.id)

        first_delivery = self.engine.generate_digest(self.db, preference.preference_id, now=_NOW)
        second_delivery = self.engine.generate_digest(self.db, preference.preference_id, now=_NOW + timedelta(hours=1))
        self.assertIsNone(second_delivery)  # no new events since the first digest — nothing to generate

        with self.db.transaction() as conn:
            digest = service.get_digest_for_delivery(conn, first_delivery.delivery_id)
        self.assertEqual(set(digest.event_ids), set(first_delivery.event_ids))

    def test_generate_digest_for_a_preference_with_no_eligible_events_returns_none(self) -> None:
        preference = self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            digest_frequency="daily",
        )
        delivery = self.engine.generate_digest(self.db, preference.preference_id, now=_NOW)
        self.assertIsNone(delivery)

    def test_generate_digest_for_unknown_preference_raises(self) -> None:
        with self.assertRaises(NotificationValidationError):
            self.engine.generate_digest(self.db, "does-not-exist", now=_NOW)


class NotificationEngineAcknowledgeAndCancelTests(unittest.TestCase):
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

    def test_acknowledge_marks_the_delivery_acknowledged_without_deleting_history(self) -> None:
        self.engine.acknowledge(self.db, self.delivery_id, acknowledged_by="user-1", note="seen it")
        with self.db.transaction() as conn:
            delivery = service.get_delivery(conn, self.delivery_id)
            acks = service.get_acknowledgements_for_delivery(conn, self.delivery_id)
        self.assertTrue(delivery.acknowledged)
        self.assertEqual(len(acks), 1)
        self.assertEqual(acks[0].acknowledged_by, "user-1")

    def test_cancel_delivery_sets_cancelled_status(self) -> None:
        delivery = self.engine.cancel_delivery(self.db, self.delivery_id)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.CANCELLED)
        self.assertIsNone(delivery.next_attempt_at)


if __name__ == "__main__":
    unittest.main()
