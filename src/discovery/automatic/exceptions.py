"""Structured exceptions for the Automatic Platform Discovery Agent — mirrors
`src.feedback.exceptions`/`src.ranking_v2.exceptions`'s "one base class, catch one
type" shape. See docs/29_Automatic_Platform_Discovery.md.
"""

from __future__ import annotations


class DiscoveryException(Exception):
    """Base class for every exception this package raises."""


class DiscoveryConfigurationError(DiscoveryException):
    """A discovery provider is misconfigured or can't be resolved — an unknown
    `provider_id`, or `register_discovery_provider` given something that isn't a
    `DiscoveryProvider`.
    """


class DiscoveryValidationError(DiscoveryException):
    """A `DiscoveryRequest` failed validation, or a candidate URL is unusable
    (empty, unparseable) — raised before anything is written, so
    `platform_candidates` never receives a malformed row.
    """


class DiscoveryProviderError(DiscoveryException):
    """A provider was resolved but its own `discover()` raised — the discovery
    equivalent of `ConnectorConnectionError`/`GeoCalculationError`: caught by the
    pipeline so one broken provider can't take down the entire discovery run,
    recorded as a failed `DiscoveryProviderObservation` instead.
    """
