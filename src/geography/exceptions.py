"""Structured exceptions for the Geographic Intelligence Engine — mirrors
`src.connectors.sdk.exceptions`/`src.providers.exceptions`/`src.filter_engine.exceptions`'s
"one base class, catch one type" shape, applied to geo providers. See
docs/26_Geographic_Intelligence.md.
"""

from __future__ import annotations


class GeoException(Exception):
    """Base class for every exception this package raises."""


class GeoProviderConfigurationError(GeoException):
    """A geo provider is misconfigured or can't be resolved — an unknown
    `provider_id`, or `register_geo_provider` given something that isn't a
    `GeoProvider`.
    """


class GeoCalculationError(GeoException):
    """A provider was available but the actual calculation failed — the geo
    equivalent of `ConnectorConnectionError`/`OllamaAIProviderError`: caught by
    callers that want to fall back to a different provider or degrade gracefully,
    never left to propagate as a bare exception.
    """
