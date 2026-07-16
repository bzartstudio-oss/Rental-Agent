"""`WebhookNotificationChannel` — disabled until a URL is configured, HMAC
signing, an idempotency-key header, and the domain allow/deny lists. Never
sends to a real endpoint in tests — a mock `HttpTransport` stands in for
`UrllibHttpTransport`.
"""

from __future__ import annotations

import hashlib
import hmac
import unittest
from datetime import datetime, timezone

from src.notifications.channels.webhook_channel import HttpPostResult, WebhookNotificationChannel
from src.notifications.models import NotificationMessage

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


class _MockHttpTransport:
    def __init__(self, *, result: HttpPostResult | None = None) -> None:
        self.result = result or HttpPostResult(status_code=200, body="ok")
        self.calls = []

    def post(self, url, *, headers, payload_json, timeout) -> HttpPostResult:
        self.calls.append({"url": url, "headers": headers, "payload_json": payload_json, "timeout": timeout})
        return self.result


def _message(**overrides) -> NotificationMessage:
    fields = dict(
        delivery_id="d1", profile_id="p1", event_ids=["e1"], channel="webhook", body_text="A new match was found.",
        template_name="immediate_apartment_alert", template_version=1, language="en", generated_at=_NOW,
        subject="New Match",
    )
    fields.update(overrides)
    return NotificationMessage(**fields)


class WebhookNotificationChannelTests(unittest.TestCase):
    def test_disabled_without_a_url(self) -> None:
        channel = WebhookNotificationChannel({})
        self.assertFalse(channel.validate_configuration())

    def test_enabled_once_a_url_is_configured(self) -> None:
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify"})
        self.assertTrue(channel.validate_configuration())

    def test_send_posts_json_through_the_mock_transport(self) -> None:
        transport = _MockHttpTransport()
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify", "transport": transport})
        result = channel.send(_message())
        self.assertTrue(result.success)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["url"], "https://hooks.example.com/notify")
        self.assertIn('"subject": "New Match"', transport.calls[0]["payload_json"])

    def test_every_send_carries_an_idempotency_key_header_equal_to_delivery_id(self) -> None:
        transport = _MockHttpTransport()
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify", "transport": transport})
        channel.send(_message(delivery_id="delivery-xyz"))
        self.assertEqual(transport.calls[0]["headers"]["Idempotency-Key"], "delivery-xyz")

    def test_signing_secret_produces_a_verifiable_hmac_signature(self) -> None:
        transport = _MockHttpTransport()
        secret = "webhook-signing-secret"
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify", "signing_secret": secret, "transport": transport})
        channel.send(_message())
        payload_json = transport.calls[0]["payload_json"]
        expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()
        self.assertEqual(transport.calls[0]["headers"]["X-Signature-256"], expected)

    def test_no_signature_header_when_no_signing_secret_configured(self) -> None:
        transport = _MockHttpTransport()
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify", "transport": transport})
        channel.send(_message())
        self.assertNotIn("X-Signature-256", transport.calls[0]["headers"])

    def test_denied_domain_is_rejected_even_with_an_explicit_url(self) -> None:
        channel = WebhookNotificationChannel({"url": "https://evil.example.com/hook", "denied_domains": ["evil.example.com"]})
        self.assertFalse(channel.validate_configuration())
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "invalid_configuration")

    def test_allowed_domains_list_rejects_anything_not_on_it(self) -> None:
        channel = WebhookNotificationChannel({"url": "https://random.example.com/hook", "allowed_domains": ["hooks.trusted.com"]})
        self.assertFalse(channel.validate_configuration())

    def test_allowed_domains_list_permits_a_subdomain_match(self) -> None:
        transport = _MockHttpTransport()
        channel = WebhookNotificationChannel({
            "url": "https://alerts.hooks.trusted.com/hook", "allowed_domains": ["hooks.trusted.com"], "transport": transport,
        })
        self.assertTrue(channel.validate_configuration())
        result = channel.send(_message())
        self.assertTrue(result.success)

    def test_non_http_scheme_is_rejected(self) -> None:
        channel = WebhookNotificationChannel({"url": "ftp://hooks.example.com/hook"})
        self.assertFalse(channel.validate_configuration())

    def test_http_error_status_is_categorized_by_status_code(self) -> None:
        transport = _MockHttpTransport(result=HttpPostResult(status_code=500, body=None))
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify", "transport": transport})
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "server_error")

    def test_client_rejection_status_is_categorized_as_rejected(self) -> None:
        transport = _MockHttpTransport(result=HttpPostResult(status_code=400, body=None))
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify", "transport": transport})
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "rejected")

    def test_transport_error_is_categorized_as_connection_error_and_redacted(self) -> None:
        secret = "webhook-signing-secret"
        transport = _MockHttpTransport(result=HttpPostResult(status_code=None, body=None, error=f"could not connect ({secret})"))
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify", "signing_secret": secret, "transport": transport})
        result = channel.send(_message())
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "connection_error")
        self.assertNotIn(secret, result.error)

    def test_preview_never_posts(self) -> None:
        transport = _MockHttpTransport()
        channel = WebhookNotificationChannel({"url": "https://hooks.example.com/notify", "transport": transport})
        channel.preview(_message())
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
