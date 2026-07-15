"""`FilterFactory` — the sanctioned way to resolve a filter by key, mirroring
`ProviderFactory`'s same thin-delegation shape (v2.5 Step 8) for the same reason: two
classes for two reasons to change — the registry is where filters *live*, the
factory is how callers *ask* for one.
"""

from __future__ import annotations

from src.filter_engine.base_filter import BaseFilter
from src.filter_engine.registry import FilterRegistry


class FilterFactory:
    @staticmethod
    def get(key: str) -> BaseFilter:
        """`FilterRegistry.get()` already raises `FilterConfigurationError` — never a
        bare `KeyError` — for an unknown key; this adds no logic of its own.
        """
        return FilterRegistry.get(key)
