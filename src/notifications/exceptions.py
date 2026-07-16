"""Structured exceptions for the Notification Delivery Engine — mirrors
`src.monitoring.exceptions`/`src.discovery.automatic.exceptions`'s "one base
class, catch one type" shape.
"""

from __future__ import annotations


class NotificationException(Exception):
    """Base class for every exception this package raises."""


class NotificationConfigurationError(NotificationException):
    """A channel is misconfigured, disabled, or can't be resolved — e.g. the
    Email channel with no SMTP host configured, or an unknown channel name.
    """


class NotificationValidationError(NotificationException):
    """A preference, message, or delivery request failed validation before
    anything was written.
    """


class NotificationDeliveryError(NotificationException):
    """A channel was resolved but its own `send()` raised unexpectedly — the
    notification equivalent of `ConnectorConnectionError`: caught by the
    engine so one channel's failure can't take down another channel's
    delivery, recorded as a failed `NotificationAttempt` instead.
    """
