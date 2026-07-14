"""Weighted-sum scoring — see docs/08_Ranking_System.md "Design: Scoring Mirrors the
Filter Registry" and "Scoring Approach: Weighted Sum". A criterion registered in
search/criteria.py without a `score` function (e.g. min_bedrooms — a pure cutoff)
contributes nothing to score; only criteria with a `score` function do.
"""

from __future__ import annotations

from src.search.criteria import extract_value, extract_weight, get_filter
from src.storage.models import Apartment


def score_apartment(apartment: Apartment, criteria: dict) -> tuple[float, dict]:
    """Returns (total_score, breakdown) where breakdown maps criterion key -> its
    weighted contribution — persisted verbatim as search_results.score_breakdown_json
    so a report can show *why* an apartment ranked where it did.
    """
    breakdown: dict[str, float] = {}
    total = 0.0

    for key, raw_value in criteria.items():
        definition = get_filter(key)
        if definition.score is None:
            continue

        value = extract_value(raw_value)
        weight = extract_weight(raw_value)
        contribution = definition.score(apartment, value) * weight

        breakdown[key] = contribution
        total += contribution

    return total, breakdown
