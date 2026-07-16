"""Listing removal state machine. See docs/30_Continuous_Monitoring.md
"Listing Removal Logic" — "Do not mark a listing removed after one failed
observation" (the mission's own words): a listing only becomes
`confirmed_removed` after `policy.removed_listing_threshold` *consecutive*
misses, with `possibly_removed` as the honest in-between state.

`consecutive_absences()` takes an already-fetched, newest-first list of
observed-apartment-id sets rather than querying the database itself — "Batch
apartment comparisons where possible" (the mission's own words): the caller
(`engine.py`) fetches each prior run's observed set once, then every
apartment's absence count is a pure in-memory computation.
"""

from __future__ import annotations

from src.monitoring.models import MonitoringPolicy

MISSING = "missing"
PRESENT = "present"
POSSIBLY_REMOVED = "possibly_removed"
CONFIRMED_REMOVED = "confirmed_removed"


def consecutive_absences(observed_sets_newest_first: list[set[str]], apartment_id: str) -> int:
    """How many consecutive prior monitoring runs (most recent first) this
    apartment was absent from, stopping at the first run where it was present.
    """
    count = 0
    for observed in observed_sets_newest_first:
        if apartment_id in observed:
            break
        count += 1
    return count


def classify_missing(consecutive_miss_count: int, policy: MonitoringPolicy) -> str:
    if consecutive_miss_count <= 0:
        return PRESENT
    if consecutive_miss_count < policy.stale_listing_threshold:
        return MISSING
    if consecutive_miss_count < policy.removed_listing_threshold:
        return POSSIBLY_REMOVED
    return CONFIRMED_REMOVED


def just_crossed_removal_threshold(consecutive_miss_count: int, policy: MonitoringPolicy) -> bool:
    """True only on the exact run where a listing crosses into
    `confirmed_removed` — so `LISTING_REMOVED` fires once, not on every
    subsequent run it stays missing.
    """
    return consecutive_miss_count == policy.removed_listing_threshold
