"""The Notification Delivery Engine — consumes stored `MonitoringEvent`s and
delivers user-approved notifications through interchangeable channels. See
docs/31_Notification_Delivery.md.

Importing this package imports `notifications.channels` and
`notifications.templates`, which is what runs every built-in channel's/
template's self-registration call. Public API re-exported here so callers
don't need to know this package's internal file layout — mirrors
`src.monitoring`/`src.discovery.automatic`'s own re-export shape.
"""

from __future__ import annotations

from src.notifications import channels as _channels  # noqa: F401 — self-registration side effect
from src.notifications import templates as _templates  # noqa: F401 — self-registration side effect
from src.notifications.base_channel import NotificationChannel
from src.notifications.base_template import NotificationTemplate, RenderedTemplate, TemplateContext
from src.notifications.exceptions import (
    NotificationConfigurationError,
    NotificationDeliveryError,
    NotificationException,
    NotificationValidationError,
)
from src.notifications.engine import NotificationEngine
from src.notifications.factory import NotificationChannelFactory
from src.notifications.metadata import NotificationChannelMetadata
from src.notifications.models import (
    NotificationAttempt,
    NotificationBatch,
    NotificationChannelResult,
    NotificationConfiguration,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationDigest,
    NotificationEligibility,
    NotificationHealth,
    NotificationMessage,
    NotificationPolicy,
    NotificationPreference,
    NotificationPreferenceVersion,
    NotificationStatistics,
)
from src.notifications.registry import NotificationChannelRegistry, register_notification_channel
from src.notifications.template_registry import NotificationTemplateRegistry, register_notification_template

__all__ = [
    "NotificationChannel",
    "NotificationEngine",
    "NotificationTemplate",
    "RenderedTemplate",
    "TemplateContext",
    "NotificationException",
    "NotificationConfigurationError",
    "NotificationDeliveryError",
    "NotificationValidationError",
    "NotificationChannelFactory",
    "NotificationChannelMetadata",
    "NotificationAttempt",
    "NotificationBatch",
    "NotificationChannelResult",
    "NotificationConfiguration",
    "NotificationDelivery",
    "NotificationDeliveryStatus",
    "NotificationDigest",
    "NotificationEligibility",
    "NotificationHealth",
    "NotificationMessage",
    "NotificationPolicy",
    "NotificationPreference",
    "NotificationPreferenceVersion",
    "NotificationStatistics",
    "NotificationChannelRegistry",
    "register_notification_channel",
    "NotificationTemplateRegistry",
    "register_notification_template",
]
