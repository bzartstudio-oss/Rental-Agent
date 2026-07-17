"""CLI tests for `src/ui/notification_cli.py` — mirrors
`tests/ui/test_monitoring_cli.py`'s own "drive `main()` against a real temp
database, assert on stdout" shape.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from src.monitoring.models import MonitoringEventType
from src.notifications import NotificationEngine, service
from src.storage.database import Database
from src.ui import notification_cli
from tests.notifications import helpers

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


class NotificationCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.saved_search = helpers.make_saved_search(self.db, profile_id="profile-1")
        with self.db.transaction() as conn:
            self.run = helpers.make_run(conn, self.saved_search)
            self.apartment = helpers.make_apartment(conn)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _run(self, argv: list[str]) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = notification_cli.main(argv, db=self.db)
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()

    def _preference_id(self) -> str:
        with self.db.transaction() as conn:
            return service.get_all_preferences(conn)[0].preference_id

    def test_create_and_list_preferences(self) -> None:
        output = self._run(["create-preference", "--profile-id", "profile-1", "--channels", "console", "file"])
        self.assertIn("Created notification preference", output)

        listing = self._run(["list-preferences"])
        self.assertIn("profile=profile-1", listing)

    def test_view_preference_shows_channels_and_version(self) -> None:
        self._run(["create-preference", "--profile-id", "profile-1", "--channels", "console"])
        view = self._run(["view-preference", "--preference-id", self._preference_id()])
        self.assertIn("version=1", view)
        self.assertIn("['console']", view)

    def test_update_preference_creates_a_new_version(self) -> None:
        self._run(["create-preference", "--profile-id", "profile-1", "--channels", "console"])
        output = self._run(["update-preference", "--preference-id", self._preference_id(), "--channels", "console", "file"])
        self.assertIn("Created version 2", output)

    def test_enable_disable_round_trip(self) -> None:
        self._run(["create-preference", "--profile-id", "profile-1", "--channels", "console"])
        preference_id = self._preference_id()
        self._run(["disable-notifications", "--preference-id", preference_id])
        with self.db.transaction() as conn:
            self.assertFalse(service.get_preference(conn, preference_id).enabled)
        self._run(["enable-notifications", "--preference-id", preference_id])
        with self.db.transaction() as conn:
            self.assertTrue(service.get_preference(conn, preference_id).enabled)

    def test_send_test_notification_via_console(self) -> None:
        self._run(["create-preference", "--profile-id", "profile-1", "--channels", "console"])
        output = self._run(["send-test-notification", "--preference-id", self._preference_id(), "--channel", "console"])
        self.assertIn("success=True", output)

    def test_deliver_pending_and_list_deliveries(self) -> None:
        self._run([
            "create-preference", "--profile-id", "profile-1", "--saved-search-id", self.saved_search.saved_search_id,
            "--channels", "console", "--immediate-event-types", MonitoringEventType.NEW_MATCH,
        ])
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)

        deliver_output = self._run(["deliver-pending"])
        self.assertIn("succeeded=1", deliver_output)

        listing = self._run(["list-deliveries", "--profile-id", "profile-1"])
        self.assertIn("status=delivered", listing)

    def test_generate_digest_manual(self) -> None:
        self._run([
            "create-preference", "--profile-id", "profile-1", "--saved-search-id", self.saved_search.saved_search_id,
            "--channels", "console", "--digest-event-types", MonitoringEventType.PRICE_DECREASED, "--digest-frequency", "daily",
        ])
        with self.db.transaction() as conn:
            # `generate-digest` (via the CLI, exercised through `_run()`) always uses the real
            # wall-clock now — it has no `--now` override — so the fixture event must be stamped
            # "just now" too, not the module's fixed historical `_NOW`, or it silently falls
            # outside the daily digest's 24h lookback window once enough real time has passed
            # since `_NOW` was chosen (this test used to intermittently fail for exactly that
            # reason).
            helpers.make_event(
                conn, self.saved_search, self.run, event_type=MonitoringEventType.PRICE_DECREASED,
                apartment_id=self.apartment.id, now=datetime.now(timezone.utc),
            )

        output = self._run(["generate-digest", "--preference-id", self._preference_id()])
        self.assertIn("Digest delivery:", output)
        self.assertNotIn("nothing generated", output)

    def test_acknowledge_and_export_history(self) -> None:
        self._run([
            "create-preference", "--profile-id", "profile-1", "--saved-search-id", self.saved_search.saved_search_id,
            "--channels", "console", "--immediate-event-types", MonitoringEventType.NEW_MATCH,
        ])
        with self.db.transaction() as conn:
            helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)
        self._run(["deliver-pending"])

        with self.db.transaction() as conn:
            delivery_id = service.get_deliveries_for_profile(conn, "profile-1")[0].delivery_id

        ack_output = self._run(["acknowledge-notification", "--delivery-id", delivery_id])
        self.assertIn("Acknowledged delivery", ack_output)

        history = self._run(["export-history", "--profile-id", "profile-1"])
        self.assertIn('"acknowledged": true', history)

    def test_channel_health_reports_console(self) -> None:
        output = self._run(["channel-health", "--channel", "console"])
        self.assertIn("channel=console", output)

    def test_task_scheduler_examples(self) -> None:
        output = self._run(["task-scheduler-examples"])
        self.assertIn("cron_deliver", output)
        self.assertIn("windows_task_scheduler", output)

    def test_view_unknown_preference_returns_nonzero_exit(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = notification_cli.main(["view-preference", "--preference-id", "does-not-exist"], db=self.db)
        self.assertEqual(exit_code, 1)
        self.assertIn("No such preference", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
