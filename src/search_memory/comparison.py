"""Pure comparison utilities for Search Memory — no database access. Mirrors the
discipline established in src/history/comparison.py (v2.0 Step 2): anything that needs
to read stored history (reconstructing "the price as of a given search," which apartments
changed between two timestamps) lives in search_memory_service.py instead, so what's
here stays independently unit-testable without a database.
"""

from __future__ import annotations

from src.search_memory.models import PlatformCoverageChange


def diff_apartment_sets(previous_ids: set[str], current_ids: set[str]) -> tuple[list[str], list[str]]:
    """New/removed apartment ids between two searches' full observed sets
    (`search_observed_apartments` — not the ranked/filtered `search_results`, see
    docs/17_Search_Memory.md). Sorted for deterministic, reproducible output.
    """
    new_ids = sorted(current_ids - previous_ids)
    removed_ids = sorted(previous_ids - current_ids)
    return new_ids, removed_ids


def platform_coverage_change(
    previous_searched_ids: list[str], current_searched_ids: list[str]
) -> PlatformCoverageChange:
    previous_set, current_set = set(previous_searched_ids), set(current_searched_ids)
    return PlatformCoverageChange(
        newly_searched_platform_ids=sorted(current_set - previous_set),
        no_longer_searched_platform_ids=sorted(previous_set - current_set),
    )


def search_quality(apartment_count: int | None, searched_platform_count: int) -> float | None:
    """A simple, deterministic proxy for "how much did this search actually cover" —
    apartments observed per successfully-searched platform. Not a prediction or a
    weighted/tuned score (that's the Knowledge Engine's `reliability_score`, explicitly
    out of scope here) — just arithmetic over already-known counts.
    """
    if apartment_count is None or searched_platform_count == 0:
        return None
    return apartment_count / searched_platform_count
