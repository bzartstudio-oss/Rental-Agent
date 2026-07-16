"""`NotificationChannelMetadata` — a channel's static self-description,
mirroring `EventDetectorMetadata`/`DiscoveryProviderMetadata`'s same
declarative-capability-discovery role.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationChannelMetadata:
    channel_name: str
    display_name: str
    description: str
    requires_configuration: bool = False
    supports_html: bool = False
    supports_attachments: bool = False
