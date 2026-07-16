"""`compute_statistics()` — computed *from* one run's already-persisted events,
never inside `MonitoringEngine` itself. Mirrors
`discovery/automatic/statistics.py`'s own "single responsibility" separation.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from statistics import mean

from src.monitoring import service
from src.monitoring.models import MonitoringComparison, MonitoringStatistics, RankChange
from src.search_memory import search_memory_service
from src.storage import search_repository


def compute_statistics(
    conn: sqlite3.Connection, monitoring_run_id: str, *, suppressed_duplicate_count: int,
    platforms_succeeded_count: int, platforms_failed_count: int, now: datetime,
) -> MonitoringStatistics:
    events = service.get_events_for_run(conn, monitoring_run_id)

    counts_by_type: dict[str, int] = {}
    for event in events:
        counts_by_type[event.event_type] = counts_by_type.get(event.event_type, 0) + 1

    significances = [event.significance for event in events]

    return MonitoringStatistics(
        monitoring_run_id=monitoring_run_id, computed_at=now, event_counts_by_type=counts_by_type,
        suppressed_duplicate_count=suppressed_duplicate_count, platforms_succeeded_count=platforms_succeeded_count,
        platforms_failed_count=platforms_failed_count, average_significance=mean(significances) if significances else None,
    )


def compare_monitoring_runs(conn: sqlite3.Connection, previous_run_id: str, current_run_id: str) -> MonitoringComparison:
    """"Compare with previous monitoring run" (the mission's own workflow
    step), exposed directly for the CLI's `compare-runs` command — reuses
    `SearchComparison` and each run's own persisted `search_results`, the same
    evidence `RankingChangeDetector` uses during a live run.
    """
    previous_run = service.get_run(conn, previous_run_id)
    current_run = service.get_run(conn, current_run_id)
    if previous_run is None or current_run is None:
        raise ValueError("Both monitoring run ids must refer to existing monitoring_runs rows")

    search_comparison = None
    if previous_run.search_id and current_run.search_id:
        search_comparison = search_memory_service.compare_searches(conn, previous_run.search_id, current_run.search_id)

    rank_changes: list[RankChange] = []
    better_match_id = None
    if previous_run.search_id and current_run.search_id:
        previous_results = {r.apartment_id: r for r in search_repository.get_search_results(conn, previous_run.search_id)}
        current_results = {r.apartment_id: r for r in search_repository.get_search_results(conn, current_run.search_id)}
        for apartment_id, current in current_results.items():
            previous = previous_results.get(apartment_id)
            if previous is None:
                continue
            rank_changes.append(
                RankChange(apartment_id=apartment_id, previous_rank=previous.rank, current_rank=current.rank,
                           previous_score=previous.score, current_score=current.score)
            )
        current_top = next((r for r in current_results.values() if r.rank == 1), None)
        previous_top = next((r for r in previous_results.values() if r.rank == 1), None)
        if current_top is not None and previous_top is not None and current_top.apartment_id != previous_top.apartment_id:
            better_match_id = current_top.apartment_id

    return MonitoringComparison(
        previous_monitoring_run_id=previous_run_id, current_monitoring_run_id=current_run_id,
        search_comparison=search_comparison, rank_changes=rank_changes, better_match_apartment_id=better_match_id,
    )
