"""Structured exceptions for the Continuous Monitoring Engine — mirrors
`src.discovery.automatic.exceptions`/`src.feedback.exceptions`'s "one base
class, catch one type" shape.
"""

from __future__ import annotations


class MonitoringException(Exception):
    """Base class for every exception this package raises."""


class MonitoringConfigurationError(MonitoringException):
    """An event detector is misconfigured or can't be resolved, or a saved
    search references a platform/connector that no longer exists.
    """


class MonitoringValidationError(MonitoringException):
    """A saved search or version failed validation before anything was
    written — e.g. an empty name, or a monitoring policy with contradictory
    scheduling fields.
    """


class MonitoringRunClaimError(MonitoringException):
    """Raised when a caller tries to operate on a run claim it doesn't hold —
    e.g. releasing a claim never acquired.
    """
