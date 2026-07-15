"""Eagerly imports every built-in filter module so each one's `register_filter(...)`
call runs — the same eager, small-known-set self-registration
`src.analysis.analyzers`/`src.providers.data`/`src.providers.ai` already established,
not `ConnectorRegistry`'s lazy per-platform import.
"""

from __future__ import annotations

from src.filter_engine.filters import amenities as _amenities  # noqa: F401
from src.filter_engine.filters import core_filters as _core_filters  # noqa: F401
from src.filter_engine.filters import distance_filters as _distance_filters  # noqa: F401
from src.filter_engine.filters import preferences_and_other as _preferences_and_other  # noqa: F401
