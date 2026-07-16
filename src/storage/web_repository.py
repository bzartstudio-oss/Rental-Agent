"""Persistence for `web_jobs`/`web_ui_preferences`/`web_saved_comparisons`/
`web_recent_views` (migration 0011, v2.5 Step 16) — pure data access; deciding
*when*/*what* to record is `src/web/`'s job. Mirrors `monitoring_repository.py`'s
exact shape.

Mutation functions in this file, and no others:
- `update_job` (web_jobs is a current-state row, like `monitoring_runs`)
- `set_ui_preference` (web_ui_preferences is a current-state row, upserted by
  its own UNIQUE(profile_id, key) constraint)

`web_saved_comparisons`/`web_recent_views` are strictly append-only.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from src.storage.models import (
    WebJobRecord,
    WebRecentViewRecord,
    WebSavedComparisonRecord,
    WebUIPreferenceRecord,
)
from src.storage.models import iso, parse_iso


# --------------------------------------------------------------------------- #
# web_jobs
# --------------------------------------------------------------------------- #


def add_job(conn: sqlite3.Connection, record: WebJobRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO web_jobs
            (job_id, job_type, profile_id, request_reference, status, progress, current_stage,
             result_reference, error_summary, warnings_json, cancellation_requested, metadata_json,
             created_at, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.job_id, record.job_type, record.profile_id, record.request_reference, record.status,
            record.progress, record.current_stage, record.result_reference, record.error_summary,
            json.dumps(record.warnings), int(record.cancellation_requested), json.dumps(record.metadata),
            iso(record.created_at), iso(record.started_at) if record.started_at else None,
            iso(record.completed_at) if record.completed_at else None,
        ),
    )
    return cursor.lastrowid


def update_job(conn: sqlite3.Connection, record: WebJobRecord) -> None:
    """Refreshes every mutable field for an existing job — `job_id`/`job_type`/
    `profile_id`/`request_reference`/`created_at` (identity) never change.
    """
    conn.execute(
        """
        UPDATE web_jobs SET
            status = ?, progress = ?, current_stage = ?, result_reference = ?, error_summary = ?,
            warnings_json = ?, cancellation_requested = ?, metadata_json = ?, started_at = ?, completed_at = ?
        WHERE job_id = ?
        """,
        (
            record.status, record.progress, record.current_stage, record.result_reference, record.error_summary,
            json.dumps(record.warnings), int(record.cancellation_requested), json.dumps(record.metadata),
            iso(record.started_at) if record.started_at else None,
            iso(record.completed_at) if record.completed_at else None,
            record.job_id,
        ),
    )


def get_job(conn: sqlite3.Connection, job_id: str) -> WebJobRecord | None:
    row = conn.execute("SELECT * FROM web_jobs WHERE job_id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row is not None else None


def get_recent_jobs(conn: sqlite3.Connection, *, profile_id: str | None = None, limit: int = 20) -> list[WebJobRecord]:
    if profile_id is not None:
        rows = conn.execute(
            "SELECT * FROM web_jobs WHERE profile_id = ? ORDER BY created_at DESC LIMIT ?", (profile_id, limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM web_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_job(row) for row in rows]


def get_active_jobs(conn: sqlite3.Connection) -> list[WebJobRecord]:
    rows = conn.execute(
        "SELECT * FROM web_jobs WHERE status IN ('pending', 'running') ORDER BY created_at DESC"
    ).fetchall()
    return [_row_to_job(row) for row in rows]


def _row_to_job(row: sqlite3.Row) -> WebJobRecord:
    return WebJobRecord(
        id=row["id"], job_id=row["job_id"], job_type=row["job_type"], profile_id=row["profile_id"],
        request_reference=row["request_reference"], status=row["status"], progress=row["progress"],
        current_stage=row["current_stage"], result_reference=row["result_reference"],
        error_summary=row["error_summary"], warnings=json.loads(row["warnings_json"]),
        cancellation_requested=bool(row["cancellation_requested"]), metadata=json.loads(row["metadata_json"]),
        created_at=parse_iso(row["created_at"]),
        started_at=parse_iso(row["started_at"]) if row["started_at"] else None,
        completed_at=parse_iso(row["completed_at"]) if row["completed_at"] else None,
    )


# --------------------------------------------------------------------------- #
# web_ui_preferences
# --------------------------------------------------------------------------- #


def set_ui_preference(conn: sqlite3.Connection, record: WebUIPreferenceRecord) -> None:
    conn.execute(
        """
        INSERT INTO web_ui_preferences (profile_id, key, value_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(profile_id, key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
        """,
        (record.profile_id, record.key, json.dumps(record.value), iso(record.updated_at)),
    )


def get_ui_preference(conn: sqlite3.Connection, profile_id: str, key: str) -> WebUIPreferenceRecord | None:
    row = conn.execute(
        "SELECT * FROM web_ui_preferences WHERE profile_id = ? AND key = ?", (profile_id, key)
    ).fetchone()
    return _row_to_preference(row) if row is not None else None


def get_all_ui_preferences(conn: sqlite3.Connection, profile_id: str) -> list[WebUIPreferenceRecord]:
    rows = conn.execute("SELECT * FROM web_ui_preferences WHERE profile_id = ?", (profile_id,)).fetchall()
    return [_row_to_preference(row) for row in rows]


def _row_to_preference(row: sqlite3.Row) -> WebUIPreferenceRecord:
    return WebUIPreferenceRecord(
        id=row["id"], profile_id=row["profile_id"], key=row["key"], value=json.loads(row["value_json"]),
        updated_at=parse_iso(row["updated_at"]),
    )


# --------------------------------------------------------------------------- #
# web_saved_comparisons
# --------------------------------------------------------------------------- #


def add_saved_comparison(conn: sqlite3.Connection, record: WebSavedComparisonRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO web_saved_comparisons (comparison_id, profile_id, name, apartment_ids_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (record.comparison_id, record.profile_id, record.name, json.dumps(record.apartment_ids), iso(record.created_at)),
    )
    return cursor.lastrowid


def get_saved_comparison(conn: sqlite3.Connection, comparison_id: str) -> WebSavedComparisonRecord | None:
    row = conn.execute("SELECT * FROM web_saved_comparisons WHERE comparison_id = ?", (comparison_id,)).fetchone()
    return _row_to_comparison(row) if row is not None else None


def get_recent_comparisons(conn: sqlite3.Connection, *, profile_id: str | None = None, limit: int = 10) -> list[WebSavedComparisonRecord]:
    if profile_id is not None:
        rows = conn.execute(
            "SELECT * FROM web_saved_comparisons WHERE profile_id = ? ORDER BY created_at DESC LIMIT ?", (profile_id, limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM web_saved_comparisons ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_comparison(row) for row in rows]


def _row_to_comparison(row: sqlite3.Row) -> WebSavedComparisonRecord:
    return WebSavedComparisonRecord(
        id=row["id"], comparison_id=row["comparison_id"], profile_id=row["profile_id"], name=row["name"],
        apartment_ids=json.loads(row["apartment_ids_json"]), created_at=parse_iso(row["created_at"]),
    )


# --------------------------------------------------------------------------- #
# web_recent_views
# --------------------------------------------------------------------------- #


def record_recent_view(conn: sqlite3.Connection, record: WebRecentViewRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO web_recent_views (profile_id, apartment_id, viewed_at) VALUES (?, ?, ?)",
        (record.profile_id, record.apartment_id, iso(record.viewed_at)),
    )
    return cursor.lastrowid


def get_recent_views(conn: sqlite3.Connection, *, profile_id: str | None = None, limit: int = 10) -> list[WebRecentViewRecord]:
    if profile_id is not None:
        rows = conn.execute(
            "SELECT * FROM web_recent_views WHERE profile_id = ? ORDER BY viewed_at DESC LIMIT ?", (profile_id, limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM web_recent_views ORDER BY viewed_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_view(row) for row in rows]


def _row_to_view(row: sqlite3.Row) -> WebRecentViewRecord:
    return WebRecentViewRecord(
        id=row["id"], profile_id=row["profile_id"], apartment_id=row["apartment_id"], viewed_at=parse_iso(row["viewed_at"]),
    )
