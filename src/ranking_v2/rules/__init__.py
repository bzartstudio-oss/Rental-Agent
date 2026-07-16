"""Eagerly imports every built-in ranking rule module so each one self-registers
into `RankingRuleRegistry` on import — mirrors `src/filter_engine/filters/__init__.py`
and `src/geography/providers/__init__.py`'s exact pattern.
"""

from __future__ import annotations

from src.ranking_v2.rules import (  # noqa: F401
    availability_rules,
    context_rules,
    geo_rules,
    price_rules,
    reliability_rules,
)
