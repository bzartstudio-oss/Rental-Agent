"""Eagerly imports every built-in data provider so its `register_provider(...)` call
runs — the same eager, small-known-set self-registration `src.analysis.analyzers`
established, not `ConnectorRegistry`'s lazy per-platform import.
"""

from __future__ import annotations

from src.providers.data import local_demo_data_provider as _local_demo_data_provider  # noqa: F401
from src.providers.data import rentcast_data_provider as _rentcast_data_provider  # noqa: F401
