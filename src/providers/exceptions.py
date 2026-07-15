"""Structured exceptions for the Provider abstraction layer — mirrors
`src.connectors.sdk.exceptions`'s "one base class, catch one type" shape, applied to
providers instead of connectors.
"""

from __future__ import annotations


class ProviderException(Exception):
    """Base class for every exception this package raises."""


class NoProviderAvailableError(ProviderException):
    """Every registered provider of the requested kind was either unavailable or
    failed when actually tried. Raised by `ProviderRouter.run_with_fallback()` only
    after every ranked candidate has been attempted — never for "kind has zero
    registered providers at all," which is a configuration bug, not a runtime
    fallback exhaustion (both still raise this, but the message distinguishes them).
    """


class ProviderConfigurationError(ProviderException):
    """A provider is misconfigured in a way that isn't just "temporarily unavailable"
    — e.g. `register_provider` given something that isn't a `Provider`.
    """


class ProviderValidationError(ProviderException):
    """Raised by `ProviderValidator.validate()` only when asked to validate strictly
    (mirrors `ConnectorValidationError`'s opt-in-only role) — a provider's declared
    `ProviderMetadata` has a score outside `[0, 1]`, or a `DataProvider` result's own
    connector-level validation already failed. Never raised by default; see
    `ProviderValidator` for what "strict" actually checks.
    """
