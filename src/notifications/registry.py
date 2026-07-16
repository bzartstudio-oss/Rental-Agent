"""Where every installed notification channel is known — mirrors
`DiscoveryProviderRegistry`/`MonitoringRegistry`'s self-registration +
eager-import shape. "Future channels must be addable without modifying
NotificationEngine" (the mission's own words) is this registry's entire
reason to exist.
"""

from __future__ import annotations

from src.notifications.base_channel import NotificationChannel
from src.notifications.exceptions import NotificationConfigurationError


class NotificationChannelRegistry:
    _channels: dict[str, NotificationChannel] = {}

    @classmethod
    def register(cls, channel: NotificationChannel) -> NotificationChannel:
        if not isinstance(channel, NotificationChannel):
            raise NotificationConfigurationError(
                f"{channel!r} is not a NotificationChannel instance — register_notification_channel() "
                "must be called with an instantiated NotificationChannel subclass"
            )
        if not getattr(channel, "channel_name", None):
            raise NotificationConfigurationError(
                f"{type(channel).__name__} must set a class-level `channel_name` before it can be registered"
            )
        cls._channels[channel.channel_name] = channel
        return channel

    @classmethod
    def get(cls, channel_name: str) -> NotificationChannel:
        try:
            return cls._channels[channel_name]
        except KeyError:
            raise NotificationConfigurationError(
                f"No notification channel registered for {channel_name!r}. Registered: {sorted(cls._channels)}"
            ) from None

    @classmethod
    def all(cls) -> list[NotificationChannel]:
        return list(cls._channels.values())

    @classmethod
    def enabled(cls) -> list[NotificationChannel]:
        """Only channels that are currently, genuinely configured — "disabled
        by default unless valid configuration is supplied" (the mission's own
        words) is enforced here, at the one place callers ask "what can I
        actually use right now."
        """
        return [channel for channel in cls._channels.values() if channel.is_enabled()]

    @classmethod
    def is_registered(cls, channel_name: str) -> bool:
        return channel_name in cls._channels

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered channel. Real code never calls this."""
        cls._channels.clear()


def register_notification_channel(channel: NotificationChannel) -> NotificationChannel:
    return NotificationChannelRegistry.register(channel)
