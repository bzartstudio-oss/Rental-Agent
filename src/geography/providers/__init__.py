"""Eagerly imports every built-in geo provider module so each one self-registers
into `GeoProviderRegistry` on import — mirrors `src/filter_engine/filters/__init__.py`
and `src/providers/data/__init__.py`'s exact pattern. Adding a future provider means
adding one import line here, never touching `GeographicEngine`/`GeoProviderRegistry`.
"""

from __future__ import annotations

from src.geography.providers import haversine_provider  # noqa: F401
