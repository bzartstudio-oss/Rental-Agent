"""Cross-cutting security/privacy checks from the mission's own "Verify"
checklist: no notification without an explicit opt-in preference, and no
channel ever echoes a configured secret back through its serialized result.
Per-channel redaction/path-traversal/URL-allowlist details are already
covered in `test_email_channel.py`/`test_webhook_channel.py`/
`test_file_channel.py` — this module only covers what's genuinely
cross-cutting.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.monitoring.models import MonitoringEventType
from src.notifications import NotificationEngine, service
from src.notifications.channels.email_channel import EmailNotificationChannel
from src.notifications.channels.webhook_channel import WebhookNotificationChannel
from src.storage.database import Database
from tests.notifications import helpers

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


class NoOptInNoDeliveryTests(unittest.TestCase):
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

    def test_an_event_with_no_matching_preference_produces_no_delivery_to_anyone(self) -> None:
        """No preference exists anywhere for this profile — an event must
        never notify a profile that never explicitly opted in.
        """
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        batch = self.engine.process_pending_deliveries(self.db, now=_NOW)
        self.assertEqual(batch.deliveries_attempted, 0)
        with self.db.transaction() as conn:
            self.assertEqual(service.get_deliveries_for_profile(conn, "profile-1"), [])

    def test_a_disabled_preference_does_not_receive_notifications(self) -> None:
        preference = self.engine.create_preference(
            self.db, "profile-1", saved_search_id=self.saved_search.saved_search_id, enabled_channels=["console"],
            immediate_event_types=[MonitoringEventType.NEW_MATCH],
        )
        self.engine.set_enabled(self.db, preference.preference_id, False)
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        self.engine.process_pending_deliveries(self.db, now=_NOW)
        with self.db.transaction() as conn:
            self.assertEqual(service.get_deliveries_for_profile(conn, "profile-1"), [])


class SecretRedactionAcrossChannelsTests(unittest.TestCase):
    """"Redact secrets from logs and exceptions" (the mission's own words) —
    a channel's `serialize_result()`/`preview()` must never echo the
    configuration it was given, regardless of success or failure.
    """

    def test_email_channel_never_echoes_password_in_channel_info_or_config(self) -> None:
        channel = EmailNotificationChannel({"smtp_host": "smtp.example.com", "sender_address": "a@example.com", "smtp_password": "hunter2"})
        info = channel.channel_info()
        self.assertNotIn("hunter2", str(info))
        self.assertNotIn("hunter2", repr(channel.channel_info()))

    def test_webhook_channel_never_echoes_signing_secret_in_channel_info(self) -> None:
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/x", "signing_secret": "super-secret"})
        info = channel.channel_info()
        self.assertNotIn("super-secret", str(info))


if __name__ == "__main__":
    unittest.main()
