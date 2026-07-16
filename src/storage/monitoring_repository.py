"""Persistence for `saved_searches`/`saved_search_versions`/`monitoring_schedules`/
`monitoring_runs`/`monitoring_events`/`event_acknowledgements`/
`monitoring_statistics`/`report_artifacts` (migration 0009, v2.5 Step 14) — pure
data access; deciding *when*/*what* to record is `src/monitoring/`'s job.
Mirrors `discovery_repository.py`'s exact shape.

Mutation functions in this file, and no others:
- `update_saved_search_metadata` (saved_searches is a current-state row, like `platforms`)
- `update_schedule` / `claim_due_run` / `release_run_claim` (monitoring_schedules is
  current-state + the run-claim lock)
- `update_run_status` (monitoring_runs' one finalize-on-completion field, like
  `discovery_runs.update_run_summary`)
- `acknowledge_event` (monitoring_events' one current-state flag)

Every other table/function is strictly append-only.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from src.storage.models import (
    EventAcknowledgementRecord,
    MonitoringEventRecord,
    MonitoringRunRecord,
    MonitoringScheduleRecord,
    MonitoringStatisticsRecord,
    ReportArtifactRecord,
    SavedSearchRecord,
    SavedSearchVersionRecord,
)
from src.storage.models import iso, parse_iso


# --------------------------------------------------------------------------- #
# saved_searches
# --------------------------------------------------------------------------- #


def add_saved_search(conn: sqlite3.Connection, record: SavedSearchRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO saved_searches
            (saved_search_id, profile_id, name, description, current_version, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.saved_search_id, record.profile_id, record.name, record.description,
            record.current_version, int(record.enabled), iso(record.created_at), iso(record.updated_at),
        ),
    )
    return cursor.lastrowid


def update_saved_search_metadata(conn: sqlite3.Connection, record: SavedSearchRecord) -> None:
    """Refreshes `name`/`description`/`current_version`/`enabled`/`updated_at` for an
    existing saved search — `saved_search_id`/`created_at` (identity/history) never
    change. The search *definition* itself never updates here; that's always a new
    `SavedSearchVersionRecord` (see `add_saved_search_version`).
    """
    conn.execute(
        """
        UPDATE saved_searches SET
            name = ?, description = ?, current_version = ?, enabled = ?, updated_at = ?
        WHERE saved_search_id = ?
        """,
        (record.name, record.description, record.current_version, int(record.enabled), iso(record.updated_at), record.saved_search_id),
    )


def get_saved_search(conn: sqlite3.Connection, saved_search_id: str) -> SavedSearchRecord | None:
    row = conn.execute("SELECT * FROM saved_searches WHERE saved_search_id = ?", (saved_search_id,)).fetchone()
    return _row_to_saved_search(row) if row is not None else None


def get_all_saved_searches(conn: sqlite3.Connection, *, enabled_only: bool = False) -> list[SavedSearchRecord]:
    where = "WHERE enabled = 1" if enabled_only else ""
    rows = conn.execute(f"SELECT * FROM saved_searches {where} ORDER BY created_at").fetchall()
    return [_row_to_saved_search(row) for row in rows]


def _row_to_saved_search(row: sqlite3.Row) -> SavedSearchRecord:
    return SavedSearchRecord(
        id=row["id"], saved_search_id=row["saved_search_id"], profile_id=row["profile_id"], name=row["name"],
        description=row["description"], current_version=row["current_version"], enabled=bool(row["enabled"]),
        created_at=parse_iso(row["created_at"]), updated_at=parse_iso(row["updated_at"]),
    )


# --------------------------------------------------------------------------- #
# saved_search_versions (append-only)
# --------------------------------------------------------------------------- #


def add_saved_search_version(conn: sqlite3.Connection, record: SavedSearchVersionRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO saved_search_versions
            (saved_search_id, version, request_json, active_filters_json, ranking_profile_json, feedback_mode,
             selected_platforms_json, selected_connectors_json, geographic_destinations_json,
             monitoring_policy_json, report_options_json, retention_policy_json, tags_json, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.saved_search_id, record.version, json.dumps(record.request), json.dumps(record.active_filters),
            json.dumps(record.ranking_profile) if record.ranking_profile is not None else None, record.feedback_mode,
            json.dumps(record.selected_platforms), json.dumps(record.selected_connectors),
            json.dumps(record.geographic_destinations), json.dumps(record.monitoring_policy),
            json.dumps(record.report_options), json.dumps(record.retention_policy), json.dumps(record.tags),
            json.dumps(record.metadata), iso(record.created_at),
        ),
    )
    return cursor.lastrowid


def get_saved_search_version(conn: sqlite3.Connection, saved_search_id: str, version: int) -> SavedSearchVersionRecord | None:
    row = conn.execute(
        "SELECT * FROM saved_search_versions WHERE saved_search_id = ? AND version = ?", (saved_search_id, version),
    ).fetchone()
    return _row_to_version(row) if row is not None else None


def get_saved_search_versions(conn: sqlite3.Connection, saved_search_id: str) -> list[SavedSearchVersionRecord]:
    rows = conn.execute(
        "SELECT * FROM saved_search_versions WHERE saved_search_id = ? ORDER BY version", (saved_search_id,),
    ).fetchall()
    return [_row_to_version(row) for row in rows]


def get_latest_saved_search_version(conn: sqlite3.Connection, saved_search_id: str) -> SavedSearchVersionRecord | None:
    row = conn.execute(
        "SELECT * FROM saved_search_versions WHERE saved_search_id = ? ORDER BY version DESC LIMIT 1", (saved_search_id,),
    ).fetchone()
    return _row_to_version(row) if row is not None else None


def _row_to_version(row: sqlite3.Row) -> SavedSearchVersionRecord:
    return SavedSearchVersionRecord(
        id=row["id"], saved_search_id=row["saved_search_id"], version=row["version"],
        request=json.loads(row["request_json"]), active_filters=json.loads(row["active_filters_json"]),
        ranking_profile=json.loads(row["ranking_profile_json"]) if row["ranking_profile_json"] else None,
        feedback_mode=row["feedback_mode"], selected_platforms=json.loads(row["selected_platforms_json"]),
        selected_connectors=json.loads(row["selected_connectors_json"]),
        geographic_destinations=json.loads(row["geographic_destinations_json"]),
        monitoring_policy=json.loads(row["monitoring_policy_json"]), report_options=json.loads(row["report_options_json"]),
        retention_policy=json.loads(row["retention_policy_json"]), tags=json.loads(row["tags_json"]),
        metadata=json.loads(row["metadata_json"]), created_at=parse_iso(row["created_at"]),
    )


# --------------------------------------------------------------------------- #
# monitoring_schedules (current-state + run-claim lock)
# --------------------------------------------------------------------------- #


def add_schedule(conn: sqlite3.Connection, record: MonitoringScheduleRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO monitoring_schedules
            (saved_search_id, next_run_at, last_run_at, last_run_status, claimed_by, claimed_at, claim_expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.saved_search_id, iso(record.next_run_at) if record.next_run_at else None,
            iso(record.last_run_at) if record.last_run_at else None, record.last_run_status, record.claimed_by,
            iso(record.claimed_at) if record.claimed_at else None,
            iso(record.claim_expires_at) if record.claim_expires_at else None,
        ),
    )
    return cursor.lastrowid


def get_schedule(conn: sqlite3.Connection, saved_search_id: str) -> MonitoringScheduleRecord | None:
    row = conn.execute("SELECT * FROM monitoring_schedules WHERE saved_search_id = ?", (saved_search_id,)).fetchone()
    return _row_to_schedule(row) if row is not None else None


def get_due_schedules(conn: sqlite3.Connection, now: datetime) -> list[MonitoringScheduleRecord]:
    """Enabled saved searches whose `next_run_at` has arrived and whose claim (if
    any) has expired — "enabled saved searches and next run time" (the mission's
    own index). Does not itself claim anything; see `claim_due_run()`.
    """
    rows = conn.execute(
        """
        SELECT ms.* FROM monitoring_schedules ms
        JOIN saved_searches ss ON ss.saved_search_id = ms.saved_search_id
        WHERE ss.enabled = 1
          AND ms.next_run_at IS NOT NULL AND ms.next_run_at <= ?
          AND (ms.claimed_by IS NULL OR ms.claim_expires_at < ?)
        ORDER BY ms.next_run_at
        """,
        (iso(now), iso(now)),
    ).fetchall()
    return [_row_to_schedule(row) for row in rows]


def claim_due_run(conn: sqlite3.Connection, saved_search_id: str, claimed_by: str, claimed_at: datetime, claim_expires_at: datetime) -> bool:
    """Atomically claims a saved search's due run — the single conditional
    `UPDATE` that makes "two workers can't claim the same run" true on SQLite
    without a separate locking mechanism: the `WHERE` clause only matches a row
    with no live claim, so a second, concurrent call sees zero rows affected.
    Returns whether *this* call won the claim.
    """
    cursor = conn.execute(
        """
        UPDATE monitoring_schedules SET claimed_by = ?, claimed_at = ?, claim_expires_at = ?
        WHERE saved_search_id = ? AND (claimed_by IS NULL OR claim_expires_at < ?)
        """,
        (claimed_by, iso(claimed_at), iso(claim_expires_at), saved_search_id, iso(claimed_at)),
    )
    return cursor.rowcount > 0


def release_run_claim(conn: sqlite3.Connection, saved_search_id: str) -> None:
    conn.execute(
        "UPDATE monitoring_schedules SET claimed_by = NULL, claimed_at = NULL, claim_expires_at = NULL WHERE saved_search_id = ?",
        (saved_search_id,),
    )


def update_schedule(conn: sqlite3.Connection, record: MonitoringScheduleRecord) -> None:
    """Refreshes `next_run_at`/`last_run_at`/`last_run_status` — used by
    `mark_run_started`/`mark_run_completed`/`mark_run_failed` (see
    `src/monitoring/scheduling.py`). Does not touch the claim fields; release
    the claim explicitly via `release_run_claim()`.
    """
    conn.execute(
        """
        UPDATE monitoring_schedules SET next_run_at = ?, last_run_at = ?, last_run_status = ?
        WHERE saved_search_id = ?
        """,
        (
            iso(record.next_run_at) if record.next_run_at else None,
            iso(record.last_run_at) if record.last_run_at else None,
            record.last_run_status, record.saved_search_id,
        ),
    )


def _row_to_schedule(row: sqlite3.Row) -> MonitoringScheduleRecord:
    return MonitoringScheduleRecord(
        id=row["id"], saved_search_id=row["saved_search_id"],
        next_run_at=parse_iso(row["next_run_at"]) if row["next_run_at"] else None,
        last_run_at=parse_iso(row["last_run_at"]) if row["last_run_at"] else None,
        last_run_status=row["last_run_status"], claimed_by=row["claimed_by"],
        claimed_at=parse_iso(row["claimed_at"]) if row["claimed_at"] else None,
        claim_expires_at=parse_iso(row["claim_expires_at"]) if row["claim_expires_at"] else None,
    )


# --------------------------------------------------------------------------- #
# monitoring_runs
# --------------------------------------------------------------------------- #


def add_run(conn: sqlite3.Connection, record: MonitoringRunRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO monitoring_runs
            (monitoring_run_id, saved_search_id, saved_search_version, search_id, status, started_at,
             completed_at, platforms_attempted_json, platforms_succeeded_json, platforms_failed_json,
             event_count, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.monitoring_run_id, record.saved_search_id, record.saved_search_version, record.search_id,
            record.status, iso(record.started_at), iso(record.completed_at) if record.completed_at else None,
            json.dumps(record.platforms_attempted), json.dumps(record.platforms_succeeded),
            json.dumps(record.platforms_failed), record.event_count, record.notes,
        ),
    )
    return cursor.lastrowid


def update_run_status(conn: sqlite3.Connection, monitoring_run_id: str, record: MonitoringRunRecord) -> None:
    """The one place `monitoring_runs` is updated after insertion — finalizing
    `status`/`completed_at`/platform outcome lists/`event_count`/`notes` once the
    run finishes, exactly like `discovery_runs.update_run_summary()`.
    """
    conn.execute(
        """
        UPDATE monitoring_runs SET
            status = ?, search_id = ?, completed_at = ?, platforms_succeeded_json = ?,
            platforms_failed_json = ?, event_count = ?, notes = ?
        WHERE monitoring_run_id = ?
        """,
        (
            record.status, record.search_id, iso(record.completed_at) if record.completed_at else None,
            json.dumps(record.platforms_succeeded), json.dumps(record.platforms_failed), record.event_count,
            record.notes, monitoring_run_id,
        ),
    )


def get_run(conn: sqlite3.Connection, monitoring_run_id: str) -> MonitoringRunRecord | None:
    row = conn.execute("SELECT * FROM monitoring_runs WHERE monitoring_run_id = ?", (monitoring_run_id,)).fetchone()
    return _row_to_run(row) if row is not None else None


def get_runs_for_saved_search(conn: sqlite3.Connection, saved_search_id: str) -> list[MonitoringRunRecord]:
    rows = conn.execute(
        "SELECT * FROM monitoring_runs WHERE saved_search_id = ? ORDER BY started_at", (saved_search_id,),
    ).fetchall()
    return [_row_to_run(row) for row in rows]


def get_latest_run_for_saved_search(conn: sqlite3.Connection, saved_search_id: str) -> MonitoringRunRecord | None:
    row = conn.execute(
        "SELECT * FROM monitoring_runs WHERE saved_search_id = ? ORDER BY started_at DESC LIMIT 1", (saved_search_id,),
    ).fetchone()
    return _row_to_run(row) if row is not None else None


def get_all_runs(conn: sqlite3.Connection) -> list[MonitoringRunRecord]:
    rows = conn.execute("SELECT * FROM monitoring_runs ORDER BY started_at").fetchall()
    return [_row_to_run(row) for row in rows]


def _row_to_run(row: sqlite3.Row) -> MonitoringRunRecord:
    return MonitoringRunRecord(
        id=row["id"], monitoring_run_id=row["monitoring_run_id"], saved_search_id=row["saved_search_id"],
        saved_search_version=row["saved_search_version"], search_id=row["search_id"], status=row["status"],
        started_at=parse_iso(row["started_at"]), completed_at=parse_iso(row["completed_at"]) if row["completed_at"] else None,
        platforms_attempted=json.loads(row["platforms_attempted_json"]),
        platforms_succeeded=json.loads(row["platforms_succeeded_json"]),
        platforms_failed=json.loads(row["platforms_failed_json"]), event_count=row["event_count"], notes=row["notes"],
    )


# --------------------------------------------------------------------------- #
# monitoring_events (append-only, `acknowledged` is the one mutable field)
# --------------------------------------------------------------------------- #


def add_event(conn: sqlite3.Connection, record: MonitoringEventRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO monitoring_events
            (event_id, monitoring_run_id, saved_search_id, saved_search_version, search_id, apartment_id,
             platform_id, connector_id, event_type, severity, significance, old_value_json, new_value_json,
             explanation, evidence_json, detected_at, dedup_key, acknowledged, notification_eligible, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.event_id, record.monitoring_run_id, record.saved_search_id, record.saved_search_version,
            record.search_id, record.apartment_id, record.platform_id, record.connector_id, record.event_type,
            record.severity, record.significance,
            json.dumps(record.old_value) if record.old_value is not None else None,
            json.dumps(record.new_value) if record.new_value is not None else None,
            record.explanation, json.dumps(record.evidence), iso(record.detected_at), record.dedup_key,
            int(record.acknowledged), int(record.notification_eligible), json.dumps(record.metadata),
        ),
    )
    return cursor.lastrowid


def acknowledge_event(conn: sqlite3.Connection, event_id: str) -> None:
    conn.execute("UPDATE monitoring_events SET acknowledged = 1 WHERE event_id = ?", (event_id,))


def get_event(conn: sqlite3.Connection, event_id: str) -> MonitoringEventRecord | None:
    row = conn.execute("SELECT * FROM monitoring_events WHERE event_id = ?", (event_id,)).fetchone()
    return _row_to_event(row) if row is not None else None


def get_events_for_run(conn: sqlite3.Connection, monitoring_run_id: str) -> list[MonitoringEventRecord]:
    rows = conn.execute(
        "SELECT * FROM monitoring_events WHERE monitoring_run_id = ? ORDER BY detected_at", (monitoring_run_id,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def get_events_for_saved_search(
    conn: sqlite3.Connection, saved_search_id: str, *, event_type: str | None = None, severity: str | None = None,
) -> list[MonitoringEventRecord]:
    clauses, params = ["saved_search_id = ?"], [saved_search_id]
    if event_type is not None:
        clauses.append("event_type = ?")
        params.append(event_type)
    if severity is not None:
        clauses.append("severity = ?")
        params.append(severity)
    rows = conn.execute(
        f"SELECT * FROM monitoring_events WHERE {' AND '.join(clauses)} ORDER BY detected_at", params,
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def get_events_by_dedup_key(conn: sqlite3.Connection, dedup_key: str) -> list[MonitoringEventRecord]:
    rows = conn.execute(
        "SELECT * FROM monitoring_events WHERE dedup_key = ? ORDER BY detected_at DESC", (dedup_key,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def get_unacknowledged_events(conn: sqlite3.Connection) -> list[MonitoringEventRecord]:
    rows = conn.execute("SELECT * FROM monitoring_events WHERE acknowledged = 0 ORDER BY detected_at").fetchall()
    return [_row_to_event(row) for row in rows]


def _row_to_event(row: sqlite3.Row) -> MonitoringEventRecord:
    return MonitoringEventRecord(
        id=row["id"], event_id=row["event_id"], monitoring_run_id=row["monitoring_run_id"],
        saved_search_id=row["saved_search_id"], saved_search_version=row["saved_search_version"],
        search_id=row["search_id"], apartment_id=row["apartment_id"], platform_id=row["platform_id"],
        connector_id=row["connector_id"], event_type=row["event_type"], severity=row["severity"],
        significance=row["significance"],
        old_value=json.loads(row["old_value_json"]) if row["old_value_json"] else None,
        new_value=json.loads(row["new_value_json"]) if row["new_value_json"] else None,
        explanation=row["explanation"], evidence=json.loads(row["evidence_json"]),
        detected_at=parse_iso(row["detected_at"]), dedup_key=row["dedup_key"], acknowledged=bool(row["acknowledged"]),
        notification_eligible=bool(row["notification_eligible"]), metadata=json.loads(row["metadata_json"]),
    )


# --------------------------------------------------------------------------- #
# event_acknowledgements (append-only)
# --------------------------------------------------------------------------- #


def add_acknowledgement(conn: sqlite3.Connection, record: EventAcknowledgementRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO event_acknowledgements (event_id, acknowledged_at, acknowledged_by, note) VALUES (?, ?, ?, ?)",
        (record.event_id, iso(record.acknowledged_at), record.acknowledged_by, record.note),
    )
    return cursor.lastrowid


def get_acknowledgements_for_event(conn: sqlite3.Connection, event_id: str) -> list[EventAcknowledgementRecord]:
    rows = conn.execute(
        "SELECT * FROM event_acknowledgements WHERE event_id = ? ORDER BY acknowledged_at", (event_id,),
    ).fetchall()
    return [
        EventAcknowledgementRecord(
            id=row["id"], event_id=row["event_id"], acknowledged_at=parse_iso(row["acknowledged_at"]),
            acknowledged_by=row["acknowledged_by"], note=row["note"],
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# monitoring_statistics (append-only)
# --------------------------------------------------------------------------- #


def add_statistics(conn: sqlite3.Connection, record: MonitoringStatisticsRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO monitoring_statistics (monitoring_run_id, computed_at, statistics_json) VALUES (?, ?, ?)",
        (record.monitoring_run_id, iso(record.computed_at), json.dumps(record.statistics)),
    )
    return cursor.lastrowid


def get_statistics_for_run(conn: sqlite3.Connection, monitoring_run_id: str) -> MonitoringStatisticsRecord | None:
    row = conn.execute(
        "SELECT * FROM monitoring_statistics WHERE monitoring_run_id = ? ORDER BY computed_at DESC LIMIT 1",
        (monitoring_run_id,),
    ).fetchone()
    if row is None:
        return None
    return MonitoringStatisticsRecord(
        id=row["id"], monitoring_run_id=row["monitoring_run_id"], computed_at=parse_iso(row["computed_at"]),
        statistics=json.loads(row["statistics_json"]),
    )


def get_all_statistics(conn: sqlite3.Connection) -> list[MonitoringStatisticsRecord]:
    rows = conn.execute("SELECT * FROM monitoring_statistics ORDER BY computed_at").fetchall()
    return [
        MonitoringStatisticsRecord(
            id=row["id"], monitoring_run_id=row["monitoring_run_id"], computed_at=parse_iso(row["computed_at"]),
            statistics=json.loads(row["statistics_json"]),
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# report_artifacts (append-only)
# --------------------------------------------------------------------------- #


def add_report_artifact(conn: sqlite3.Connection, record: ReportArtifactRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO report_artifacts (monitoring_run_id, report_type, path, generated_at) VALUES (?, ?, ?, ?)",
        (record.monitoring_run_id, record.report_type, record.path, iso(record.generated_at)),
    )
    return cursor.lastrowid


def get_report_artifacts_for_run(conn: sqlite3.Connection, monitoring_run_id: str) -> list[ReportArtifactRecord]:
    rows = conn.execute(
        "SELECT * FROM report_artifacts WHERE monitoring_run_id = ? ORDER BY generated_at", (monitoring_run_id,),
    ).fetchall()
    return [
        ReportArtifactRecord(
            id=row["id"], monitoring_run_id=row["monitoring_run_id"], report_type=row["report_type"],
            path=row["path"], generated_at=parse_iso(row["generated_at"]),
        )
        for row in rows
    ]
