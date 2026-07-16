"""`ConsoleNotificationChannel` — zero-credential, always-enabled, text/JSON
preview modes.
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

from src.notifications.channels.console_channel import ConsoleNotificationChannel
from src.notifications.models import NotificationMessage

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


def _message(**overrides) -> NotificationMessage:
    fields = dict(
        delivery_id="d1", profile_id="p1", event_ids=["e1"], channel="console", body_text="A new match was found.",
        template_name="immediate_apartment_alert", template_version=1, language="en", generated_at=_NOW,
        subject="New Match", original_listing_urls=["https://example.com/1"], report_links=["output/monitoring/reports/r1.html"],
    )
    fields.update(overrides)
    return NotificationMessage(**fields)


class ConsoleNotificationChannelTests(unittest.TestCase):
    def test_is_always_enabled(self) -> None:
        channel = ConsoleNotificationChannel()
        self.assertTrue(channel.validate_configuration())
        self.assertTrue(channel.is_enabled())

    def test_preview_never_prints(self) -> None:
        channel = ConsoleNotificationChannel()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rendered = channel.preview(_message())
        self.assertEqual(buffer.getvalue(), "")  # preview must never perform the actual side effect
        self.assertIn("New Match", rendered)

    def test_send_prints_text_mode_including_urls_and_reports(self) -> None:
        channel = ConsoleNotificationChannel({"mode": "text"})
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = channel.send(_message())
        self.assertTrue(result.success)
        output = buffer.getvalue()
        self.assertIn("Subject: New Match", output)
        self.assertIn("https://example.com/1", output)
        self.assertIn("output/monitoring/reports/r1.html", output)

    def test_send_json_mode_is_valid_json_with_expected_keys(self) -> None:
        channel = ConsoleNotificationChannel({"mode": "json"})
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            channel.send(_message())
        parsed = json.loads(buffer.getvalue())
        self.assertEqual(parsed["subject"], "New Match")
        self.assertEqual(parsed["original_listing_urls"], ["https://example.com/1"])

    def test_channel_info_reports_no_configuration_required(self) -> None:
        info = ConsoleNotificationChannel().channel_info()
        self.assertFalse(info.requires_configuration)


if __name__ == "__main__":
    unittest.main()
