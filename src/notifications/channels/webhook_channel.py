"""`WebhookNotificationChannel` — generic HTTP webhook delivery. Disabled by
default; becomes enabled only once a destination URL is configured. See
docs/31_Notification_Delivery.md "Webhook Configuration".

`HttpTransport` is an injectable seam (mirrors
`discovery.automatic.verification.PageFetcher`'s own shape) so the test suite
never sends a real request to a real endpoint — "Tests must use a local fake
HTTP server or mock transport. Do not send to arbitrary live endpoints during
automated tests" (the mission's own words).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from src.notifications.base_channel import NotificationChannel
from src.notifications.metadata import NotificationChannelMetadata
from src.notifications.models import NotificationChannelResult, NotificationMessage
from src.notifications.registry import register_notification_channel

_DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass
class HttpPostResult:
    status_code: int | None
    body: str | None
    error: str | None = None


class HttpTransport(Protocol):
    def post(self, url: str, *, headers: dict, payload_json: str, timeout: float) -> HttpPostResult: ...


class UrllibHttpTransport:
    """The one real `HttpTransport` — a single POST, no retry of its own
    (retries are the engine's job, at the delivery level).
    """

    def post(self, url: str, *, headers: dict, payload_json: str, timeout: float) -> HttpPostResult:
        request = urllib.request.Request(url, data=payload_json.encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(1_000_000).decode("utf-8", errors="replace")
                return HttpPostResult(status_code=response.status, body=body)
        except HTTPError as exc:
            return HttpPostResult(status_code=exc.code, body=None, error=str(exc))
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            return HttpPostResult(status_code=None, body=None, error=str(exc))


class WebhookNotificationChannel(NotificationChannel):
    channel_name = "webhook"

    def configure(self, config: dict) -> None:
        super().configure(config)
        self._url = config.get("url", os.environ.get("WEBHOOK_URL"))
        self._headers = dict(config.get("headers", {}))
        self._timeout = float(config.get("timeout", _DEFAULT_TIMEOUT_SECONDS))
        self._signing_secret = config.get("signing_secret", os.environ.get("WEBHOOK_SIGNING_SECRET"))
        self._allowed_domains: list[str] = list(config.get("allowed_domains", []))
        self._denied_domains: list[str] = list(config.get("denied_domains", []))
        self._transport: HttpTransport = config.get("transport") or UrllibHttpTransport()

    def validate_configuration(self) -> bool:
        return bool(self._url) and self._is_url_allowed(self._url)

    def supports(self, capability: str) -> bool:
        return capability in ("json", "idempotency")

    def preview(self, message: NotificationMessage) -> str:
        return json.dumps(self._payload(message), indent=2)

    def send(self, message: NotificationMessage) -> NotificationChannelResult:
        started = time.monotonic()
        if not self.validate_configuration():
            return self._timed_result(self.channel_name, started, success=False, error="Webhook channel is not configured (missing/disallowed url)", error_category="invalid_configuration")

        payload = self._payload(message)
        payload_json = json.dumps(payload)
        headers = {"Content-Type": "application/json", "Idempotency-Key": message.delivery_id, **self._headers}
        if self._signing_secret:
            headers["X-Signature-256"] = self._sign(payload_json)

        result = self._transport.post(self._url, headers=headers, payload_json=payload_json, timeout=self._timeout)

        if result.error is not None:
            return self._timed_result(self.channel_name, started, success=False, error=self._redact(result.error), error_category="connection_error")
        if result.status_code is not None and 200 <= result.status_code < 300:
            return self._timed_result(self.channel_name, started, success=True, external_id=str(result.status_code))
        error_category = "server_error" if (result.status_code or 0) >= 500 or result.status_code in (408, 429) else "rejected"
        return self._timed_result(self.channel_name, started, success=False, error=f"HTTP {result.status_code}", error_category=error_category)

    def channel_info(self) -> NotificationChannelMetadata:
        return NotificationChannelMetadata(
            channel_name=self.channel_name, display_name="Webhook",
            description="Generic HTTP webhook delivery — disabled until a destination URL is configured.",
            requires_configuration=True, supports_html=False, supports_attachments=False,
        )

    def _payload(self, message: NotificationMessage) -> dict:
        return {
            "notification_id": message.notification_id, "delivery_id": message.delivery_id,
            "event_ids": message.event_ids, "subject": message.subject, "body_text": message.body_text,
            "original_listing_urls": message.original_listing_urls, "report_links": message.report_links,
            "generated_at": message.generated_at.isoformat(),
        }

    def _sign(self, payload_json: str) -> str:
        digest = hmac.new(self._signing_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def _is_url_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        if any(host == denied or host.endswith(f".{denied}") for denied in self._denied_domains):
            return False
        if self._allowed_domains and not any(host == allowed or host.endswith(f".{allowed}") for allowed in self._allowed_domains):
            return False
        return True

    def _redact(self, text: str) -> str:
        if self._signing_secret and self._signing_secret in text:
            text = text.replace(self._signing_secret, "***REDACTED***")
        return text


register_notification_channel(WebhookNotificationChannel())
