"""`FileNotificationChannel` — zero-credential, always-enabled, never
overwrites, and can't be made to write outside its configured output
directory. See docs/31_Notification_Delivery.md "Console and File Channels".
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.notifications.channels.file_channel import FileNotificationChannel
from src.notifications.models import NotificationMessage

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


def _message(**overrides) -> NotificationMessage:
    fields = dict(
        delivery_id="d1", profile_id="p1", event_ids=["e1"], channel="file", body_text="A new match was found.",
        template_name="immediate_apartment_alert", template_version=1, language="en", generated_at=_NOW,
        subject="New Match", original_listing_urls=["https://example.com/1"], metadata={"attempt_number": 1},
    )
    fields.update(overrides)
    return NotificationMessage(**fields)


class FileNotificationChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmp_dir.name) / "notifications"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_is_always_enabled(self) -> None:
        channel = FileNotificationChannel({"output_dir": self.output_dir})
        self.assertTrue(channel.is_enabled())

    def test_send_writes_a_deterministic_filename_under_the_output_dir(self) -> None:
        channel = FileNotificationChannel({"output_dir": self.output_dir, "format": "text"})
        result = channel.send(_message())
        self.assertTrue(result.success)
        expected_path = self.output_dir / "d1__attempt-1__file.txt"
        self.assertTrue(expected_path.exists())
        self.assertIn("New Match", expected_path.read_text(encoding="utf-8"))

    def test_json_format_writes_valid_json_with_original_urls(self) -> None:
        channel = FileNotificationChannel({"output_dir": self.output_dir, "format": "json"})
        channel.send(_message())
        path = self.output_dir / "d1__attempt-1__file.json"
        parsed = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["original_listing_urls"], ["https://example.com/1"])

    def test_html_format_writes_the_html_body_when_present(self) -> None:
        channel = FileNotificationChannel({"output_dir": self.output_dir, "format": "html"})
        channel.send(_message(body_html="<p>hi</p>"))
        path = self.output_dir / "d1__attempt-1__file.html"
        self.assertEqual(path.read_text(encoding="utf-8"), "<p>hi</p>")

    def test_never_overwrites_an_existing_delivery_artifact(self) -> None:
        channel = FileNotificationChannel({"output_dir": self.output_dir})
        first = channel.send(_message())
        self.assertTrue(first.success)

        second = channel.send(_message())  # same delivery_id + attempt_number + channel
        self.assertFalse(second.success)
        self.assertEqual(second.error_category, "non_retryable")
        self.assertIn("Refusing to overwrite", second.error)

    def test_a_second_attempt_number_produces_a_distinct_file_preserving_history(self) -> None:
        channel = FileNotificationChannel({"output_dir": self.output_dir})
        channel.send(_message(metadata={"attempt_number": 1}))
        second = channel.send(_message(metadata={"attempt_number": 2}))
        self.assertTrue(second.success)
        self.assertTrue((self.output_dir / "d1__attempt-1__file.txt").exists())
        self.assertTrue((self.output_dir / "d1__attempt-2__file.txt").exists())

    def test_preview_never_writes_a_file(self) -> None:
        channel = FileNotificationChannel({"output_dir": self.output_dir})
        channel.preview(_message())
        self.assertFalse(any(self.output_dir.glob("*")))

    def test_a_delivery_id_engineered_to_escape_the_output_dir_is_rejected(self) -> None:
        channel = FileNotificationChannel({"output_dir": self.output_dir})
        malicious = _message(delivery_id="../../etc/passwd")
        result = channel.send(malicious)
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "non_retryable")
        # Nothing must have been written outside the configured output directory.
        escaped_path = (self.output_dir / ".." / ".." / "etc" / "passwd").resolve()
        self.assertFalse(escaped_path.exists())


if __name__ == "__main__":
    unittest.main()
