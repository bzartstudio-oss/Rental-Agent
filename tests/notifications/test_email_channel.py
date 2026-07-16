"""`EmailNotificationChannel` — disabled until real SMTP config is supplied,
never opens a real network connection in tests (a fake `EmailTransport`
stands in for `SmtplibEmailTransport`), and never leaks the configured
password into an error message. See docs/31_Notification_Delivery.md "Email
Configuration".
"""

from __future__ import annotations

import smtplib
import unittest
from datetime import datetime, timezone

from src.notifications.channels.email_channel import EmailNotificationChannel
from src.notifications.models import NotificationMessage

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


class _FakeEmailTransport:
    """A fake `EmailTransport` — records what it was asked to send, and can be
    told to raise a specific `smtplib` exception instead, all without ever
    touching a real socket.
    """

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.raises = raises
        self.sent = []

    def send(self, message, *, host, port, username, password, use_tls, use_ssl, timeout) -> None:
        if self.raises is not None:
            raise self.raises
        self.sent.append({"message": message, "host": host, "port": port, "username": username, "password": password})


def _message(**overrides) -> NotificationMessage:
    fields = dict(
        delivery_id="d1", profile_id="p1", event_ids=["e1"], channel="email", body_text="A new match was found.",
        template_name="immediate_apartment_alert", template_version=1, language="en", generated_at=_NOW,
        subject="New Match",
    )
    fields.update(overrides)
    return NotificationMessage(**fields)


class EmailNotificationChannelTests(unittest.TestCase):
    def test_disabled_without_host_or_sender(self) -> None:
        channel = EmailNotificationChannel({})
        self.assertFalse(channel.validate_configuration())
        self.assertFalse(channel.is_enabled())

    def test_enabled_once_host_and_sender_are_configured(self) -> None:
        channel = EmailNotificationChannel({"smtp_host": "smtp.example.com", "sender_address": "alerts@example.com"})
        self.assertTrue(channel.validate_configuration())

    def test_send_without_configuration_fails_honestly_without_raising(self) -> None:
        channel = EmailNotificationChannel({})
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "invalid_configuration")

    def test_send_without_a_recipient_fails_with_invalid_configuration(self) -> None:
        channel = EmailNotificationChannel({
            "smtp_host": "smtp.example.com", "sender_address": "alerts@example.com", "transport": _FakeEmailTransport(),
        })
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "invalid_configuration")

    def test_send_succeeds_through_the_fake_transport(self) -> None:
        transport = _FakeEmailTransport()
        channel = EmailNotificationChannel({
            "smtp_host": "smtp.example.com", "sender_address": "alerts@example.com",
            "recipient_address": "user@example.com", "transport": transport,
        })
        result = channel.send(_message())
        self.assertTrue(result.success)
        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(transport.sent[0]["message"]["To"], "user@example.com")

    def test_recipient_can_be_overridden_per_message(self) -> None:
        transport = _FakeEmailTransport()
        channel = EmailNotificationChannel({
            "smtp_host": "smtp.example.com", "sender_address": "alerts@example.com",
            "recipient_address": "default@example.com", "transport": transport,
        })
        channel.send(_message(metadata={"recipient": "override@example.com"}))
        self.assertEqual(transport.sent[0]["message"]["To"], "override@example.com")

    def test_authentication_failure_is_categorized_and_password_is_redacted(self) -> None:
        secret_password = "super-secret-password"
        transport = _FakeEmailTransport(raises=smtplib.SMTPAuthenticationError(535, f"bad credentials: {secret_password}"))
        channel = EmailNotificationChannel({
            "smtp_host": "smtp.example.com", "sender_address": "alerts@example.com",
            "recipient_address": "user@example.com", "smtp_password": secret_password, "transport": transport,
        })
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "unauthorized")
        self.assertNotIn(secret_password, result.error)
        self.assertIn("REDACTED", result.error)

    def test_connection_errors_are_categorized_as_retryable_connection_error(self) -> None:
        transport = _FakeEmailTransport(raises=smtplib.SMTPServerDisconnected("connection lost"))
        channel = EmailNotificationChannel({
            "smtp_host": "smtp.example.com", "sender_address": "alerts@example.com",
            "recipient_address": "user@example.com", "transport": transport,
        })
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "connection_error")

    def test_generic_smtp_exception_is_categorized_as_server_error(self) -> None:
        transport = _FakeEmailTransport(raises=smtplib.SMTPException("mailbox full"))
        channel = EmailNotificationChannel({
            "smtp_host": "smtp.example.com", "sender_address": "alerts@example.com",
            "recipient_address": "user@example.com", "transport": transport,
        })
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "server_error")

    def test_preview_never_sends_and_never_leaks_password(self) -> None:
        transport = _FakeEmailTransport()
        channel = EmailNotificationChannel({
            "smtp_host": "smtp.example.com", "sender_address": "alerts@example.com",
            "recipient_address": "user@example.com", "smtp_password": "hunter2", "transport": transport,
        })
        rendered = channel.preview(_message())
        self.assertEqual(transport.sent, [])
        self.assertNotIn("hunter2", rendered)

    def test_serialize_result_never_echoes_configuration(self) -> None:
        channel = EmailNotificationChannel({"smtp_host": "smtp.example.com", "sender_address": "a@example.com", "smtp_password": "hunter2"})
        result = channel.send(_message())  # fails (no recipient), still must not leak config
        serialized = channel.serialize_result(result)
        self.assertNotIn("hunter2", str(serialized))


if __name__ == "__main__":
    unittest.main()
