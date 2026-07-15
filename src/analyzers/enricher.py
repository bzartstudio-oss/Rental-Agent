"""Derived fields computed once here rather than per-connector, so the calculation is
identical regardless of source platform — see docs/07_Analysis_Engine.md.

V1 keeps these as pure computed-on-read functions, not stored columns, per the open
question there: nothing here needs an external knowledge_base lookup yet, so nothing
needs to be persisted. Add a reference_data_repository-backed function here (not a new
module) when the first enrichment rule that actually needs curated reference data
shows up.
"""

from __future__ import annotations

from src.storage.models import Apartment


def price_per_sqft(apartment: Apartment) -> float | None:
    if not apartment.sqft:
        return None
    return round(apartment.current_price / apartment.sqft, 2)
