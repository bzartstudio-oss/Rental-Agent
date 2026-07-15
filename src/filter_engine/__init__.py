"""The Dynamic Filter Engine — a fully modular, plugin-based filtering system. See
docs/25_Dynamic_Filter_Engine.md.

Importing this package imports `filter_engine.filters`, which is what runs every
built-in filter's `register_filter(...)` call. Public API re-exported here so
callers don't need to know this package's internal file layout — mirrors
`src.connectors.sdk`/`src.providers`'s own re-export shape.
"""

from __future__ import annotations

from src.filter_engine import filters as _filters  # noqa: F401 — import for self-registration side effect
from src.filter_engine.base_filter import BaseFilter, FilterContext
from src.filter_engine.composition import FilterCondition, FilterGroup, FilterOperator, build_group_from_criteria, evaluate
from src.filter_engine.configuration import FilterConfiguration
from src.filter_engine.engine import FilterEngine
from src.filter_engine.exceptions import FilterConfigurationError, FilterException, FilterValidationError
from src.filter_engine.factory import FilterFactory
from src.filter_engine.history import FilterHistoryEntry, get_filter_history, record_filter_execution
from src.filter_engine.metadata import FilterMetadata
from src.filter_engine.registry import FilterRegistry, register_filter
from src.filter_engine.result import FilterResult
from src.filter_engine.statistics import FilterStatistics, compute_filter_statistics
from src.filter_engine.sync import sync_filter_definitions
from src.filter_engine.validator import FilterValidator

__all__ = [
    "BaseFilter",
    "FilterContext",
    "FilterCondition",
    "FilterGroup",
    "FilterOperator",
    "build_group_from_criteria",
    "evaluate",
    "FilterConfiguration",
    "FilterEngine",
    "FilterException",
    "FilterConfigurationError",
    "FilterValidationError",
    "FilterFactory",
    "FilterHistoryEntry",
    "record_filter_execution",
    "get_filter_history",
    "FilterMetadata",
    "FilterRegistry",
    "register_filter",
    "FilterResult",
    "FilterStatistics",
    "compute_filter_statistics",
    "sync_filter_definitions",
    "FilterValidator",
]
