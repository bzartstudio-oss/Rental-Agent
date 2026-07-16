"""Persistence for `feedback_events`/`preference_observations`/`preference_adjustments`/
`preference_snapshots` (migration 0007, v2.5 Step 12) — pure data access; deciding
*when*/*what* to record is `src/feedback/`'s job. Mirrors
`filter_history_repository.py`/`geo_history_repository.py`'s exact shape.

`feedback_events` is genuinely append-only: no `update_*`/`delete_*` function exists
here, on purpose — the only way to "change" a recorded event is to record a new one.
"""

from __future__ import annotations

import json
import sqlite3

from src.storage.models import (
    FeedbackEventRecord,
    PreferenceAdjustmentRecord,
    PreferenceObservationRecord,
    PreferenceSnapshotRecord,
)
from src.storage.models import iso, parse_iso


def add_event(conn: sqlite3.Connection, event: FeedbackEventRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO feedback_events
            (event_id, profile_id, search_id, apartment_id, event_type, event_value_json,
             occurred_at, source, session_id, metadata_json, ranking_profile_json, search_filters_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id, event.profile_id, event.search_id, event.apartment_id, event.event_type,
            json.dumps(event.event_value), iso(event.occurred_at), event.source, event.session_id,
            json.dumps(event.metadata),
            json.dumps(event.ranking_profile) if event.ranking_profile is not None else None,
            json.dumps(event.search_filters) if event.search_filters is not None else None,
        ),
    )
    return cursor.lastrowid


def get_events_for_profile(conn: sqlite3.Connection, profile_id: str) -> list[FeedbackEventRecord]:
    rows = conn.execute(
        "SELECT * FROM feedback_events WHERE profile_id = ? ORDER BY occurred_at",
        (profile_id,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def get_events_for_apartment(conn: sqlite3.Connection, apartment_id: str) -> list[FeedbackEventRecord]:
    rows = conn.execute(
        "SELECT * FROM feedback_events WHERE apartment_id = ? ORDER BY occurred_at",
        (apartment_id,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def get_event_by_id(conn: sqlite3.Connection, event_id: str) -> FeedbackEventRecord | None:
    row = conn.execute("SELECT * FROM feedback_events WHERE event_id = ?", (event_id,)).fetchone()
    return _row_to_event(row) if row is not None else None


def _row_to_event(row: sqlite3.Row) -> FeedbackEventRecord:
    return FeedbackEventRecord(
        id=row["id"], event_id=row["event_id"], profile_id=row["profile_id"], search_id=row["search_id"],
        apartment_id=row["apartment_id"], event_type=row["event_type"], event_value=json.loads(row["event_value_json"]),
        occurred_at=parse_iso(row["occurred_at"]), source=row["source"], session_id=row["session_id"],
        metadata=json.loads(row["metadata_json"]),
        ranking_profile=json.loads(row["ranking_profile_json"]) if row["ranking_profile_json"] else None,
        search_filters=json.loads(row["search_filters_json"]) if row["search_filters_json"] else None,
    )


def add_observation(conn: sqlite3.Connection, observation: PreferenceObservationRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO preference_observations
            (profile_id, preference_key, event_id, direction, magnitude, observed_value_json,
             source_type, computed_at, explanation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation.profile_id, observation.preference_key, observation.event_id, observation.direction,
            observation.magnitude,
            json.dumps(observation.observed_value) if observation.observed_value is not None else None,
            observation.source_type, iso(observation.computed_at), observation.explanation,
        ),
    )
    return cursor.lastrowid


def get_observations(conn: sqlite3.Connection, profile_id: str, preference_key: str) -> list[PreferenceObservationRecord]:
    rows = conn.execute(
        "SELECT * FROM preference_observations WHERE profile_id = ? AND preference_key = ? ORDER BY computed_at",
        (profile_id, preference_key),
    ).fetchall()
    return [_row_to_observation(row) for row in rows]


def get_all_observations_for_profile(conn: sqlite3.Connection, profile_id: str) -> list[PreferenceObservationRecord]:
    rows = conn.execute(
        "SELECT * FROM preference_observations WHERE profile_id = ? ORDER BY computed_at",
        (profile_id,),
    ).fetchall()
    return [_row_to_observation(row) for row in rows]


def _row_to_observation(row: sqlite3.Row) -> PreferenceObservationRecord:
    return PreferenceObservationRecord(
        id=row["id"], profile_id=row["profile_id"], preference_key=row["preference_key"], event_id=row["event_id"],
        direction=row["direction"], magnitude=row["magnitude"],
        observed_value=json.loads(row["observed_value_json"]) if row["observed_value_json"] else None,
        source_type=row["source_type"], computed_at=parse_iso(row["computed_at"]), explanation=row["explanation"],
    )


def add_adjustment(conn: sqlite3.Connection, adjustment: PreferenceAdjustmentRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO preference_adjustments
            (profile_id, preference_key, previous_value_json, new_value_json, previous_confidence,
             new_confidence, reason, triggered_by_event_ids_json, adjustment_type, reverses_adjustment_id, applied_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            adjustment.profile_id, adjustment.preference_key,
            json.dumps(adjustment.previous_value) if adjustment.previous_value is not None else None,
            json.dumps(adjustment.new_value) if adjustment.new_value is not None else None,
            adjustment.previous_confidence, adjustment.new_confidence, adjustment.reason,
            json.dumps(adjustment.triggered_by_event_ids), adjustment.adjustment_type,
            adjustment.reverses_adjustment_id, iso(adjustment.applied_at),
        ),
    )
    return cursor.lastrowid


def get_adjustments(conn: sqlite3.Connection, profile_id: str, preference_key: str) -> list[PreferenceAdjustmentRecord]:
    rows = conn.execute(
        "SELECT * FROM preference_adjustments WHERE profile_id = ? AND preference_key = ? ORDER BY applied_at",
        (profile_id, preference_key),
    ).fetchall()
    return [_row_to_adjustment(row) for row in rows]


def get_adjustment_by_id(conn: sqlite3.Connection, adjustment_id: int) -> PreferenceAdjustmentRecord | None:
    row = conn.execute("SELECT * FROM preference_adjustments WHERE id = ?", (adjustment_id,)).fetchone()
    return _row_to_adjustment(row) if row is not None else None


def _row_to_adjustment(row: sqlite3.Row) -> PreferenceAdjustmentRecord:
    return PreferenceAdjustmentRecord(
        id=row["id"], profile_id=row["profile_id"], preference_key=row["preference_key"],
        previous_value=json.loads(row["previous_value_json"]) if row["previous_value_json"] else None,
        new_value=json.loads(row["new_value_json"]) if row["new_value_json"] else None,
        previous_confidence=row["previous_confidence"], new_confidence=row["new_confidence"],
        reason=row["reason"], triggered_by_event_ids=json.loads(row["triggered_by_event_ids_json"]),
        adjustment_type=row["adjustment_type"], reverses_adjustment_id=row["reverses_adjustment_id"],
        applied_at=parse_iso(row["applied_at"]),
    )


def add_snapshot(conn: sqlite3.Connection, snapshot: PreferenceSnapshotRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO preference_snapshots (profile_id, snapshot_json, reason, created_at) VALUES (?, ?, ?, ?)",
        (snapshot.profile_id, json.dumps(snapshot.snapshot), snapshot.reason, iso(snapshot.created_at)),
    )
    return cursor.lastrowid


def get_snapshots(conn: sqlite3.Connection, profile_id: str) -> list[PreferenceSnapshotRecord]:
    rows = conn.execute(
        "SELECT * FROM preference_snapshots WHERE profile_id = ? ORDER BY created_at",
        (profile_id,),
    ).fetchall()
    return [
        PreferenceSnapshotRecord(
            id=row["id"], profile_id=row["profile_id"], snapshot=json.loads(row["snapshot_json"]),
            reason=row["reason"], created_at=parse_iso(row["created_at"]),
        )
        for row in rows
    ]
