"""Importing this package runs every built-in template's
`register_notification_template(...)` call.
"""

from __future__ import annotations

from src.notifications.templates import digest_templates, event_alert_templates  # noqa: F401

__all__: list[str] = []
