"""Persistence for `search_requests` and `search_results` — see docs/03_Data_Model.md
"The Versioning Principle, Concretely" for why search_results denormalizes
price_at_search/status_at_search instead of joining to live apartment data.
"""

from __future__ import annotations

import json
import sqlite3

from src.storage.models import SearchRequestRecord, SearchResultEntry, iso, parse_iso


def insert_search_request(conn: sqlite3.Connection, request: SearchRequestRecord) -> None:
    """Writes only the v1.1 columns (what was asked) — the v2.0 Search Memory columns
    (what happened) start NULL and are filled in later via an UPDATE once a run
    completes (docs/03_Data_Model.md's one deliberate exception to insert-only). That
    UPDATE is `storage/search_memory_repository.py::complete_search_execution`, called by
    `src/search_memory/search_memory_service.py::record_completed_search` from
    `RentalResearchAgent.run()` (v2.0 Step 3) — this function still only ever writes the
    columns known at submission time.
    """
    conn.execute(
        "INSERT INTO search_requests (id, created_at, label, criteria_json) VALUES (?, ?, ?, ?)",
        (request.id, iso(request.created_at), request.label, request.criteria_json),
    )


def get_search_request(conn: sqlite3.Connection, search_id: str) -> SearchRequestRecord | None:
    row = conn.execute("SELECT * FROM search_requests WHERE id = ?", (search_id,)).fetchone()
    return row_to_search_request(row) if row is not None else None


def row_to_search_request(row: sqlite3.Row) -> SearchRequestRecord:
    """Shared with storage/search_memory_repository.py (v2.0 Step 3), which reads
    `search_requests` rows for history/comparison queries and needs the exact same
    mapping — kept in one place so the two never drift apart.
    """
    return SearchRequestRecord(
        id=row["id"],
        created_at=parse_iso(row["created_at"]),
        label=row["label"],
        criteria_json=row["criteria_json"],
        # v2.0 (migration 0001) — Search Memory columns, all nullable until
        # search_memory_repository.complete_search_execution() (v2.0 Step 3) fills them
        # in once a run finishes.
        execution_time_ms=row["execution_time_ms"],
        discovered_platform_ids=json.loads(row["discovered_platform_ids_json"])
        if row["discovered_platform_ids_json"]
        else None,
        searched_platform_ids=json.loads(row["searched_platform_ids_json"])
        if row["searched_platform_ids_json"]
        else None,
        apartment_count=row["apartment_count"],
        new_apartment_count=row["new_apartment_count"],
        removed_apartment_count=row["removed_apartment_count"],
        changed_apartment_count=row["changed_apartment_count"],
        report_path=row["report_path"],
        runtime_stats=json.loads(row["runtime_stats_json"]) if row["runtime_stats_json"] else None,
    )


def add_search_result(conn: sqlite3.Connection, result: SearchResultEntry) -> int:
    cursor = conn.execute(
        """
        INSERT INTO search_results (
            search_id, apartment_id, rank, score, score_breakdown_json,
            price_at_search, status_at_search
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.search_id,
            result.apartment_id,
            result.rank,
            result.score,
            result.score_breakdown_json,
            result.price_at_search,
            result.status_at_search,
        ),
    )
    return cursor.lastrowid


def get_search_results(conn: sqlite3.Connection, search_id: str) -> list[SearchResultEntry]:
    """Ranked results for one search — this is what the Report Generator (docs/09_Report_System.md)
    reads to build output/<search_id>.html, and it never changes after the fact even if the
    underlying apartments do (that's the whole point of the snapshot columns).
    """
    rows = conn.execute(
        "SELECT * FROM search_results WHERE search_id = ? ORDER BY rank",
        (search_id,),
    ).fetchall()
    return [
        SearchResultEntry(
            id=row["id"],
            search_id=row["search_id"],
            apartment_id=row["apartment_id"],
            rank=row["rank"],
            score=row["score"],
            score_breakdown_json=row["score_breakdown_json"],
            price_at_search=row["price_at_search"],
            status_at_search=row["status_at_search"],
        )
        for row in rows
    ]
