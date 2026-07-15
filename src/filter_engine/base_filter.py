"""`BaseFilter` — the plugin contract every filter implements. See
docs/25_Dynamic_Filter_Engine.md "Filter Lifecycle".

Deliberately a thin contract with sensible defaults, not a multi-stage template
method like `BaseConnector` — a filter's whole job is one yes/no decision per
apartment, the same reasoning `BaseAnalyzer` (v2.0 Step 6) already used for exactly
this kind of "one computation, not a fetch/parse/validate sequence" component. Only
`validate()`, `apply()`, and `metadata()` are abstract; `supports()`/`description()`/
`default_value()`/`serialize()`/`deserialize()` have working defaults so a filter
that needs nothing special beyond a match rule doesn't implement eight methods to
satisfy the mission's list — it implements three and inherits the rest, exactly like
a connector inherits everything but `build_url`/`parse`/`normalize`/`connector_info`.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.analysis.models import AnalysisResult
from src.filter_engine.metadata import FilterMetadata
from src.storage.models import Apartment


@dataclass
class FilterContext:
    """What a filter may need beyond the one `Apartment` it's evaluating — mirrors
    `src.analysis.models.AnalysisContext`'s same reasoning (most analyzers only need
    the apartment; a few need more). Most built-in filters (price, bedrooms, sqft,
    images, platform) never touch this. The distance-based filters
    (`WalkingDistanceFilter`/`PublicTransportTimeFilter`/`MaximumDistanceFilter`) read
    `analysis_results` — the *same* dict `core/agent.py` already builds via
    `AnalysisEngine.analyze()` in the same search run, never a second database
    round-trip — falling back to a direct `conn` read (`analysis_metrics_repository`)
    only when used standalone, outside the full agent pipeline.
    """

    conn: sqlite3.Connection | None = None
    analysis_results: dict[str, AnalysisResult] | None = None


class BaseFilter(ABC):
    key: str

    @abstractmethod
    def validate(self, value: Any) -> None:
        """Raise `FilterValidationError` (or let a `ValueError`/`TypeError` propagate —
        `FilterEngine`'s validation stage wraps either into the structured exception)
        for a value this filter can never meaningfully apply against — e.g. a
        negative price, a non-numeric distance. Called once per criterion, before any
        `apply()` call, so a bad request fails immediately.
        """
        raise NotImplementedError

    @abstractmethod
    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        """`True` means this apartment passes this one filter. A dormant filter (see
        `FilterMetadata.is_dormant`) always returns `True` — "no evidence to exclude
        on" is never treated as "excluded," the same convention `RawListing`'s honest
        `None` fields and the Analysis Engine's `score=None` already established.
        """
        raise NotImplementedError

    def supports(self, apartment: Apartment) -> bool:
        """Whether this filter is even applicable to `apartment` at all — e.g. a
        room-sharing-specific filter against a whole-unit rental type. Default `True`
        (applicable to everything); a filter narrowing this should check
        `apartment.property_type` or similar against `metadata().applicable_rental_types`.
        """
        return True

    @abstractmethod
    def metadata(self) -> FilterMetadata:
        raise NotImplementedError

    def description(self) -> str:
        return self.metadata().description

    def default_value(self) -> Any:
        return None

    def serialize(self, value: Any) -> Any:
        """To a JSON-safe form for `criteria_json` persistence — identity by default,
        since every built-in filter's value (number/bool/string) is already
        JSON-native. Override only if a filter's value is a richer Python object.
        """
        return value

    def deserialize(self, raw: Any) -> Any:
        """The inverse of `serialize()` — identity by default."""
        return raw
