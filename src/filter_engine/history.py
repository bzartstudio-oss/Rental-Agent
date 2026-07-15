"""`FilterHistory` — records what one `FilterEngine.run()` call actually did (search
id, filter set, execution time, results count, statistics), via
`storage/filter_history_repository.py` (migration 0005). See
docs/25_Dynamic_Filter_Engine.md "Filter Pipeline" — the "Statistics" stage feeds
this "Results"/history stage, mirroring the Knowledge Engine's own
observe-then-persist shape rather than inventing a new one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from src.filter_engine.statistics import FilterStatistics
from src.storage import filter_history_repository
from src.storage.models import FilterExecutionHistoryEntry


@dataclass
class FilterHistoryEntry:
    search_id: str
    filter_set: dict
    total_apartments: int
    matched_count: int
    statistics: FilterStatistics
    recorded_at: datetime
    execution_time_ms: int | None = None


def record_filter_execution(conn: sqlite3.Connection, entry: FilterHistoryEntry) -> None:
    filter_history_repository.add_execution(
        conn,
        FilterExecutionHistoryEntry(
            search_id=entry.search_id,
            filter_set=entry.filter_set,
            execution_time_ms=entry.execution_time_ms,
            total_apartments=entry.total_apartments,
            matched_count=entry.matched_count,
            statistics=entry.statistics.as_dict(),
            recorded_at=entry.recorded_at,
        ),
    )


def get_filter_history(conn: sqlite3.Connection, search_id: str) -> list[FilterExecutionHistoryEntry]:
    return filter_history_repository.get_history_for_search(conn, search_id)
