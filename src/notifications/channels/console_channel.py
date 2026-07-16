"""`ConsoleNotificationChannel` — prints a notification preview to stdout.
Works with zero external credentials, always enabled. See
docs/31_Notification_Delivery.md "Console and File Channels".
"""

from __future__ import annotations

import json
import time

from src.notifications.base_channel import NotificationChannel
from src.notifications.metadata import NotificationChannelMetadata
from src.notifications.models import NotificationChannelResult, NotificationMessage
from src.notifications.registry import register_notification_channel


class ConsoleNotificationChannel(NotificationChannel):
    channel_name = "console"

    def configure(self, config: dict) -> None:
        super().configure(config)
        self._mode = config.get("mode", "text")  # "text" | "json"

    def validate_configuration(self) -> bool:
        return True  # no external credentials needed

    def supports(self, capability: str) -> bool:
        return capability in ("text", "json", "batch")

    def preview(self, message: NotificationMessage) -> str:
        return self._render(message)

    def send(self, message: NotificationMessage) -> NotificationChannelResult:
        started = time.monotonic()
        print(self._render(message))
        return self._timed_result(self.channel_name, started, success=True)

    def channel_info(self) -> NotificationChannelMetadata:
        return NotificationChannelMetadata(
            channel_name=self.channel_name, display_name="Console", description="Prints a notification preview to stdout — useful for local development.",
            requires_configuration=False, supports_html=False, supports_attachments=False,
        )

    def _render(self, message: NotificationMessage) -> str:
        if self._mode == "json":
            return json.dumps({
                "notification_id": message.notification_id, "subject": message.subject, "body": message.body_text,
                "event_ids": message.event_ids, "original_listing_urls": message.original_listing_urls,
                "report_links": message.report_links,
            }, indent=2)
        lines = [f"--- Notification ({message.channel}) ---"]
        if message.subject:
            lines.append(f"Subject: {message.subject}")
        lines.append(message.body_text)
        if message.original_listing_urls:
            lines.append("Listings: " + ", ".join(message.original_listing_urls))
        if message.report_links:
            lines.append("Reports: " + ", ".join(message.report_links))
        return "\n".join(lines)


register_notification_channel(ConsoleNotificationChannel())
