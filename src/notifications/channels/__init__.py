"""Importing this package runs every built-in channel's
`register_notification_channel(...)` call — mirrors
`src.discovery.automatic.providers`'s own self-registration-by-import shape.
"""

from __future__ import annotations

from src.notifications.channels import (  # noqa: F401
    console_channel,
    email_channel,
    file_channel,
    webhook_channel,
)

__all__: list[str] = []
