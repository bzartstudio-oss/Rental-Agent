"""`FileNotificationChannel` — saves a notification under
`output/notifications/`. Works with zero external credentials, always
enabled. See docs/31_Notification_Delivery.md "Console and File Channels".

Filenames are built entirely from controlled components (`delivery_id` — a
UUID — plus a small integer `attempt_number` and the channel name) — never
from freeform message content (subject/body) — which is what actually
prevents path traversal here, not a denylist. `_resolve_path()` additionally
asserts the resolved path stays inside the configured output directory as
defense in depth.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from src.core.config import OUTPUT_DIR
from src.notifications.base_channel import NotificationChannel
from src.notifications.exceptions import NotificationDeliveryError
from src.notifications.metadata import NotificationChannelMetadata
from src.notifications.models import NotificationChannelResult, NotificationMessage
from src.notifications.registry import register_notification_channel

_DEFAULT_OUTPUT_DIR = OUTPUT_DIR / "notifications"


class FileNotificationChannel(NotificationChannel):
    channel_name = "file"

    def configure(self, config: dict) -> None:
        super().configure(config)
        self._output_dir = Path(config.get("output_dir", _DEFAULT_OUTPUT_DIR))
        self._format = config.get("format", "text")  # "text" | "html" | "json"

    def validate_configuration(self) -> bool:
        return True  # no external credentials needed

    def supports(self, capability: str) -> bool:
        return capability in ("text", "html", "json", "batch")

    def preview(self, message: NotificationMessage) -> str:
        return self._render(message)

    def send(self, message: NotificationMessage) -> NotificationChannelResult:
        started = time.monotonic()
        try:
            path = self._resolve_path(message)
            if path.exists():
                # Never overwrite an existing delivery artifact — the mission's
                # own words. A collision means the same (delivery, attempt,
                # channel) tuple was asked to send twice, which should never
                # happen with a correctly-incrementing attempt_number.
                raise NotificationDeliveryError(f"Refusing to overwrite existing notification artifact: {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self._render(message), encoding="utf-8")
        except NotificationDeliveryError as exc:
            return self._timed_result(self.channel_name, started, success=False, error=str(exc), error_category="non_retryable")
        except OSError as exc:
            return self._timed_result(self.channel_name, started, success=False, error=str(exc), error_category="retryable")
        return self._timed_result(self.channel_name, started, success=True, external_id=str(path), metadata={"path": str(path)})

    def channel_info(self) -> NotificationChannelMetadata:
        return NotificationChannelMetadata(
            channel_name=self.channel_name, display_name="File",
            description="Saves notifications under output/notifications/ — text, HTML, or JSON.",
            requires_configuration=False, supports_html=True, supports_attachments=False,
        )

    def _resolve_path(self, message: NotificationMessage) -> Path:
        attempt_number = message.metadata.get("attempt_number", 1)
        extension = {"text": "txt", "html": "html", "json": "json"}.get(self._format, "txt")
        filename = f"{message.delivery_id}__attempt-{attempt_number}__{self.channel_name}.{extension}"
        resolved_dir = self._output_dir.resolve()
        path = (resolved_dir / filename).resolve()
        if resolved_dir not in path.parents and path != resolved_dir:
            raise NotificationDeliveryError(f"Resolved notification path escapes output directory: {path}")
        return path

    def _render(self, message: NotificationMessage) -> str:
        if self._format == "json":
            return json.dumps({
                "notification_id": message.notification_id, "delivery_id": message.delivery_id,
                "subject": message.subject, "body_text": message.body_text, "body_html": message.body_html,
                "event_ids": message.event_ids, "original_listing_urls": message.original_listing_urls,
                "report_links": message.report_links, "generated_at": message.generated_at.isoformat(),
            }, indent=2)
        if self._format == "html" and message.body_html:
            return message.body_html
        lines = [f"Subject: {message.subject}" if message.subject else "", message.body_text]
        if message.original_listing_urls:
            lines.append("Listings: " + ", ".join(message.original_listing_urls))
        if message.report_links:
            lines.append("Reports: " + ", ".join(message.report_links))
        return "\n".join(line for line in lines if line)


register_notification_channel(FileNotificationChannel())
