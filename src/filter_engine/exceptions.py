"""Structured exceptions for the Dynamic Filter Engine — mirrors
`src.connectors.sdk.exceptions`/`src.providers.exceptions`'s "one base class, catch
one type" shape, applied to filters. See docs/25_Dynamic_Filter_Engine.md.
"""

from __future__ import annotations


class FilterException(Exception):
    """Base class for every exception this package raises."""


class FilterConfigurationError(FilterException):
    """A filter is misconfigured or can't be resolved — an unknown `key`, a
    `register_filter` call given something that isn't a `BaseFilter`, or an
    `enabled_filter_keys` set naming a key that was never registered.
    """


class FilterValidationError(FilterException):
    """A criterion value failed one filter's own `validate()` — raised by
    `FilterEngine`'s validation stage before normalization/execution ever runs, so an
    invalid request fails immediately rather than deep in the pipeline (the same
    "fail fast" behavior `SearchRequest.__post_init__`/`search.criteria.validate_criteria`
    already established).
    """
