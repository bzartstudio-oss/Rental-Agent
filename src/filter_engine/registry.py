"""Where every installed filter is known — mirrors `AnalysisRegistry`/
`ProviderRegistry`'s self-registration + eager-import shape (a small, known set of
filters, all always candidates, unlike `ConnectorRegistry`'s lazy per-platform
imports). See docs/25_Dynamic_Filter_Engine.md "Plugin System".

Filters register **instances**, not classes — no built-in filter has any per-search
construction parameter (the criterion *value* is passed to `apply()`/`validate()` per
call, not baked into the filter at construction time), so one shared instance per
filter, registered once at import time, is correct and simpler than
`ConnectorRegistry`'s per-instantiation model.
"""

from __future__ import annotations

from src.filter_engine.base_filter import BaseFilter
from src.filter_engine.exceptions import FilterConfigurationError


class FilterRegistry:
    _filters: dict[str, BaseFilter] = {}

    @classmethod
    def register(cls, filter_instance: BaseFilter) -> BaseFilter:
        """Applied as `register_filter(SomeFilter())` at the bottom of a filter
        module — runs at import time, the same "self", not something `FilterEngine`
        has to know to do, as `register_connector`/`register_provider`.
        """
        if not isinstance(filter_instance, BaseFilter):
            raise FilterConfigurationError(
                f"{filter_instance!r} is not a BaseFilter instance — register_filter() "
                "must be called with an instantiated BaseFilter subclass"
            )
        if not getattr(filter_instance, "key", None):
            raise FilterConfigurationError(
                f"{type(filter_instance).__name__} must set a class-level `key` "
                "before it can be registered"
            )
        cls._filters[filter_instance.key] = filter_instance
        return filter_instance

    @classmethod
    def get(cls, key: str) -> BaseFilter:
        try:
            return cls._filters[key]
        except KeyError:
            raise FilterConfigurationError(
                f"No filter registered for {key!r}. Registered: {sorted(cls._filters)}"
            ) from None

    @classmethod
    def all(cls) -> list[BaseFilter]:
        return list(cls._filters.values())

    @classmethod
    def is_registered(cls, key: str) -> bool:
        return key in cls._filters

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered filter. Real code never calls this."""
        cls._filters.clear()


def register_filter(filter_instance: BaseFilter) -> BaseFilter:
    return FilterRegistry.register(filter_instance)
