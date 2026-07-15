"""Structured exceptions for the Connector SDK (v2.0 Step 5) — see
docs/18_Connector_SDK.md "Error Handling". Every SDK-raised error is a
`ConnectorException` subclass so callers (`core/agent.py`) can catch one type and
still tell *what kind* of failure happened from `type(exc)`, rather than parsing a
generic `Exception`'s message.
"""

from __future__ import annotations


class ConnectorException(Exception):
    """Base class for every exception this package raises. Catch this to mean "a
    connector-related failure happened," regardless of which stage caused it.
    """


class ConnectorConnectionError(ConnectorException):
    """Fetching failed — network error, timeout, navigation failure, non-2xx response.
    Raised by `BaseConnector`'s default `fetch_listing()`/collector wiring; a connector
    overriding the fetch mechanism (e.g. for an HTTP API) should raise this too, not a
    raw `requests`/`playwright` exception, so callers only ever need to catch one type.
    """


class ConnectorParsingError(ConnectorException):
    """The fetched response couldn't be parsed into listing records — malformed HTML/
    JSON/XML, an unexpected page structure, a missing expected element. Distinct from
    `ConnectorConnectionError`: the fetch succeeded, but what came back wasn't usable.
    """


class ConnectorValidationError(ConnectorException):
    """A listing failed validation seriously enough to be treated as an error rather
    than a warning — only raised when `ConnectorConfiguration.strict_validation` is
    `True` (the default, `False`, only ever produces warnings — see
    `ConnectorValidator`). Off by default because no existing connector's listings have
    ever needed to be rejected outright; this exists for a future connector/caller that
    wants stricter guarantees.
    """


class ConnectorConfigurationError(ConnectorException):
    """The connector itself is misconfigured or can't be resolved — an unknown
    `connector_name`, a platform with `connector_available=False`, a missing connector
    module, or (for a login-required platform) missing credentials. Raised by
    `ConnectorFactory`/`ConnectorRegistry` before a connector is ever instantiated, and
    by `BaseConnector.connect()` for connectors that need configuration to proceed.
    """
