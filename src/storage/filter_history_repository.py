"""Persistence for `filter_execution_history` (migration 0005, v2.5 Step 9) — pure
data access; deciding *when*/*what* to record is `filter_engine.history`'s job.
"""

from __future__ import annotations

import json
import sqlite3

from src.storage.models import FilterExecutionHistoryEntry, iso, parse_iso


def add_execution(conn: sqlite3.Connection, entry: FilterExecutionHistoryEntry) -> int:
    cursor = conn.execute(
        """
        INSERT INTO filter_execution_history
            (search_id, filter_set_json, execution_time_ms, total_apartments, matched_count, statistics_json, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.search_id,
            json.dumps(entry.filter_set),
            entry.execution_time_ms,
            entry.total_apartments,
            entry.matched_count,
            json.dumps(entry.statistics),
            iso(entry.recorded_at),
        ),
    )
    return cursor.lastrowid


def get_history_for_search(conn: sqlite3.Connection, search_id: str) -> list[FilterExecutionHistoryEntry]:
    rows = conn.execute(
        "SELECT * FROM filter_execution_history WHERE search_id = ? ORDER BY recorded_at",
        (search_id,),
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def _row_to_entry(row: sqlite3.Row) -> FilterExecutionHistoryEntry:
    return FilterExecutionHistoryEntry(
        id=row["id"],
        search_id=row["search_id"],
        filter_set=json.loads(row["filter_set_json"]),
        execution_time_ms=row["execution_time_ms"],
        total_apartments=row["total_apartments"],
        matched_count=row["matched_count"],
        statistics=json.loads(row["statistics_json"]),
        recorded_at=parse_iso(row["recorded_at"]),
    )
