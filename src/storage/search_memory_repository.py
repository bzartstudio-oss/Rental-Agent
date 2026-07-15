"""Persistence for Search Memory (v2.0 Step 3): `search_observed_apartments` (the full
observed set per search — schema added in migration 0001, real logic added here), the
run-stats completion `UPDATE` on `search_requests` (the one deliberate exception to
insert-only, per `insert_search_request`'s docstring), and the history/lookup queries
the read-side service needs. Same convention as every other repository module: pure
data access, no decisions about *when*/*what* to write — that's
src/search_memory/search_memory_service.py and core/agent.py's job
(docs/01_System_Architecture.md).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from src.storage.models import SearchObservedApartment, SearchRequestRecord, iso, parse_iso
from src.storage.search_repository import row_to_search_request


def add_observed_apartment(
    conn: sqlite3.Connection, search_id: str, apartment_id: str, observed_at: datetime
) -> int:
    cursor = conn.execute(
        "INSERT INTO search_observed_apartments (search_id, apartment_id, observed_at) VALUES (?, ?, ?)",
        (search_id, apartment_id, iso(observed_at)),
    )
    return cursor.lastrowid


def get_observed_apartments(conn: sqlite3.Connection, search_id: str) -> list[SearchObservedApartment]:
    rows = conn.execute(
        "SELECT * FROM search_observed_apartments WHERE search_id = ? ORDER BY observed_at",
        (search_id,),
    ).fetchall()
    return [
        SearchObservedApartment(
            id=row["id"],
            search_id=row["search_id"],
            apartment_id=row["apartment_id"],
            observed_at=parse_iso(row["observed_at"]),
        )
        for row in rows
    ]


def get_observed_apartment_ids(conn: sqlite3.Connection, search_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT apartment_id FROM search_observed_apartments WHERE search_id = ?", (search_id,)
    ).fetchall()
    return {row["apartment_id"] for row in rows}


def complete_search_execution(
    conn: sqlite3.Connection,
    search_id: str,
    *,
    execution_time_ms: int,
    discovered_platform_ids: list[str],
    searched_platform_ids: list[str],
    apartment_count: int,
    new_apartment_count: int,
    removed_apartment_count: int,
    changed_apartment_count: int,
    report_path: str,
    runtime_stats: dict,
) -> None:
    """The one deliberate exception to insert-only (docs/03_Data_Model.md): fills in the
    eight v2.0 run-stats columns left `NULL` at submission time, once
    `RentalResearchAgent.run()` actually finishes. A `UPDATE`, not an `INSERT` — these
    columns describe *this run's own execution*, which has nothing to version (there is
    only ever one true answer to "how long did this specific run take").
    """
    conn.execute(
        """
        UPDATE search_requests SET
            execution_time_ms = ?,
            discovered_platform_ids_json = ?,
            searched_platform_ids_json = ?,
            apartment_count = ?,
            new_apartment_count = ?,
            removed_apartment_count = ?,
            changed_apartment_count = ?,
            report_path = ?,
            runtime_stats_json = ?
        WHERE id = ?
        """,
        (
            execution_time_ms,
            json.dumps(discovered_platform_ids),
            json.dumps(searched_platform_ids),
            apartment_count,
            new_apartment_count,
            removed_apartment_count,
            changed_apartment_count,
            report_path,
            json.dumps(runtime_stats),
            search_id,
        ),
    )


def find_previous_search(
    conn: sqlite3.Connection, location: str, before_created_at: datetime, exclude_search_id: str | None = None
) -> SearchRequestRecord | None:
    """"Which previous run" (docs/17_Search_Memory.md "Run-Over-Run Comparison"): the
    most recent *other* search with the same `location` string, regardless of whether
    its filters match exactly — a heuristic, not a strict identity rule (a user tweaking
    `max_price` between two runs of "the same ongoing search" is the common case; exact
    `criteria_json` matching would mean almost no two runs ever compare).

    Fetches every earlier `search_requests` row and filters by location in Python
    (`criteria_json` isn't indexed) — fine at this project's current scale; revisit with
    an indexed `location` column if search history ever grows large enough to matter.
    """
    rows = conn.execute(
        "SELECT * FROM search_requests WHERE created_at < ? ORDER BY created_at DESC",
        (iso(before_created_at),),
    ).fetchall()
    for row in rows:
        if row["id"] == exclude_search_id:
            continue
        if _location_from_criteria_json(row["criteria_json"]) == location:
            return row_to_search_request(row)
    return None


def get_search_history(
    conn: sqlite3.Connection, location: str | None = None, limit: int | None = None
) -> list[SearchRequestRecord]:
    """Newest-first. `location=None` returns every search ever made, across all
    locations — used for global statistics as well as per-location history/timelines.
    """
    rows = conn.execute("SELECT * FROM search_requests ORDER BY created_at DESC").fetchall()
    records = []
    for row in rows:
        if location is not None and _location_from_criteria_json(row["criteria_json"]) != location:
            continue
        records.append(row_to_search_request(row))
        if limit is not None and len(records) >= limit:
            break
    return records


def _location_from_criteria_json(criteria_json: str) -> str:
    return json.loads(criteria_json).get("location", "")
