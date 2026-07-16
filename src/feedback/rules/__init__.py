"""Eagerly imports every built-in preference rule module so each one self-registers
into `FeedbackRegistry` on import — mirrors `src/ranking_v2/rules/__init__.py`/
`src/geography/providers/__init__.py`'s exact pattern.
"""

from __future__ import annotations

from src.feedback.rules import amenity_rules, geo_rules, listing_rules, price_rules  # noqa: F401
