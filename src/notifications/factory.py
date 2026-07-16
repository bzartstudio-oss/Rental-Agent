"""`NotificationChannelFactory` — the sanctioned way to resolve a channel by
name, mirroring `DiscoveryProviderFactory`'s own thin-delegation shape.
"""

from __future__ import annotations

from src.notifications.base_channel import NotificationChannel
from src.notifications.registry import NotificationChannelRegistry


class NotificationChannelFactory:
    @staticmethod
    def get(channel_name: str) -> NotificationChannel:
        return NotificationChannelRegistry.get(channel_name)

    @staticmethod
    def resolve(channel_names: list[str] | None) -> list[NotificationChannel]:
        """`None` resolves to every currently-*enabled* channel; an explicit
        list resolves to exactly those (regardless of enabled state — a
        caller naming a specific channel is asking directly, and a disabled
        channel's own `send()` will honestly refuse rather than being
        silently skipped).
        """
        if channel_names is None:
            return NotificationChannelRegistry.enabled()
        return [NotificationChannelFactory.get(name) for name in channel_names]
