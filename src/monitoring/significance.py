"""Deterministic change-significance scoring. See
docs/30_Continuous_Monitoring.md "Change Significance" — "Implement
deterministic significance calculation ... Do not hardcode one universal
threshold" (the mission's own words): every function here is a plain,
explainable ratio or fixed constant, and every threshold it's compared against
comes from the caller's own `MonitoringPolicy`, never a hidden module-level
constant.
"""

from __future__ import annotations


def price_change_significance(old_price: float | None, new_price: float | None) -> float:
    """The fraction of the old price the change represents, capped at 1.0 — a
    100%+ swing is maximally significant, not literally unbounded.
    """
    if not old_price or new_price is None:
        return 0.0
    return min(1.0, abs(new_price - old_price) / old_price)


def availability_change_significance(became_available_or_unavailable: bool) -> float:
    """A flip between "available" and "not available" is always highly
    significant; any other status text change (e.g. wording only) is honestly
    scored lower — it may not represent a real availability change at all.
    """
    return 1.0 if became_available_or_unavailable else 0.3


def new_match_significance(*, is_first_ever_listing: bool) -> float:
    """A brand-new listing (never seen by any search before) is more
    significant than an existing listing simply newly matching this saved
    search for the first time.
    """
    return 1.0 if is_first_ever_listing else 0.6


def rank_change_significance(rank_delta: int, total_candidates: int) -> float:
    if total_candidates <= 1:
        return 0.0
    return min(1.0, abs(rank_delta) / total_candidates)


def better_match_significance(score_delta: float, threshold: float) -> float:
    if not threshold:
        return 0.0
    return min(1.0, max(0.0, score_delta / threshold))


LISTING_REMOVED = 0.8
LISTING_RETURNED = 0.7
FILTER_MATCH_GAINED = 0.5
FILTER_MATCH_LOST = 0.5
CONNECTOR_FAILURE = 0.5
CONNECTOR_RECOVERED = 0.3
PLATFORM_BECAME_ACCESSIBLE = 0.3
PLATFORM_BECAME_INACCESSIBLE = 0.5
DISCOVERY_FOUND_NEW_PLATFORM = 0.4
LISTING_UPDATED = 0.2


def severity_for_significance(significance: float) -> str:
    if significance >= 0.7:
        return "critical"
    if significance >= 0.4:
        return "warning"
    return "info"
