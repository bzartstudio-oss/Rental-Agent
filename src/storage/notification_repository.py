"""Persistence for `notification_preferences`/`notification_preference_versions`/
`notification_templates`/`notification_batches`/`notification_deliveries`/
`notification_delivery_events`/`notification_digests`/`notification_attempts`/
`notification_messages`/`rate_limit_observations`/`channel_health_observations`/
`notification_acknowledgements` (migration 0010, v2.5 Step 15) — pure data
access; deciding *when*/*what* to record is `src/notifications/`'s job. Mirrors
`monitoring_repository.py`'s exact shape.

Mutation functions in this file, and no others:
- `update_preference_metadata` (notification_preferences is a current-state row)
- `update_batch` (notification_batches finalizes counters on completion)
- `update_delivery` / `acknowledge_delivery` (notification_deliveries is
  current-state; `acknowledged` doubles as the one flag flip)

Every other table/function is strictly append-only.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from src.storage.models import (
    ChannelHealthObservationRecord,
    NotificationAcknowledgementRecord,
    NotificationAttemptRecord,
    NotificationBatchRecord,
    NotificationDeliveryEventRecord,
    NotificationDeliveryRecord,
    NotificationDigestRecord,
    NotificationMessageRecord,
    NotificationPreferenceRecord,
    NotificationPreferenceVersionRecord,
    NotificationTemplateRecord,
    RateLimitObservationRecord,
)
from src.storage.models import iso, parse_iso


# --------------------------------------------------------------------------- #
# notification_preferences
# --------------------------------------------------------------------------- #


def add_preference(conn: sqlite3.Connection, record: NotificationPreferenceRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_preferences
            (preference_id, profile_id, saved_search_id, current_version, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.preference_id, record.profile_id, record.saved_search_id, record.current_version,
            int(record.enabled), iso(record.created_at), iso(record.updated_at),
        ),
    )
    return cursor.lastrowid


def update_preference_metadata(conn: sqlite3.Connection, record: NotificationPreferenceRecord) -> None:
    conn.execute(
        "UPDATE notification_preferences SET current_version = ?, enabled = ?, updated_at = ? WHERE preference_id = ?",
        (record.current_version, int(record.enabled), iso(record.updated_at), record.preference_id),
    )


def get_preference(conn: sqlite3.Connection, preference_id: str) -> NotificationPreferenceRecord | None:
    row = conn.execute("SELECT * FROM notification_preferences WHERE preference_id = ?", (preference_id,)).fetchone()
    return _row_to_preference(row) if row is not None else None


def get_all_preferences(
    conn: sqlite3.Connection, *, profile_id: str | None = None, enabled_only: bool = False,
) -> list[NotificationPreferenceRecord]:
    clauses, params = [], []
    if profile_id is not None:
        clauses.append("profile_id = ?")
        params.append(profile_id)
    if enabled_only:
        clauses.append("enabled = 1")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM notification_preferences {where} ORDER BY created_at", params).fetchall()
    return [_row_to_preference(row) for row in rows]


def _row_to_preference(row: sqlite3.Row) -> NotificationPreferenceRecord:
    return NotificationPreferenceRecord(
        id=row["id"], preference_id=row["preference_id"], profile_id=row["profile_id"],
        saved_search_id=row["saved_search_id"], current_version=row["current_version"], enabled=bool(row["enabled"]),
        created_at=parse_iso(row["created_at"]), updated_at=parse_iso(row["updated_at"]),
    )


# --------------------------------------------------------------------------- #
# notification_preference_versions (append-only)
# --------------------------------------------------------------------------- #


def add_preference_version(conn: sqlite3.Connection, record: NotificationPreferenceVersionRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_preference_versions
            (preference_id, version, enabled_channels_json, event_types_json, minimum_severity,
             minimum_significance, immediate_event_types_json, digest_event_types_json, digest_frequency,
             quiet_hours_start, quiet_hours_end, timezone, max_per_hour, max_per_day, include_images,
             include_original_urls, include_ranking_explanation, include_geo_summary,
             include_preference_explanation, include_report_links, language, format, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.preference_id, record.version, json.dumps(record.enabled_channels), json.dumps(record.event_types),
            record.minimum_severity, record.minimum_significance, json.dumps(record.immediate_event_types),
            json.dumps(record.digest_event_types), record.digest_frequency, record.quiet_hours_start,
            record.quiet_hours_end, record.timezone, record.max_per_hour, record.max_per_day,
            int(record.include_images), int(record.include_original_urls), int(record.include_ranking_explanation),
            int(record.include_geo_summary), int(record.include_preference_explanation), int(record.include_report_links),
            record.language, record.format, json.dumps(record.metadata), iso(record.created_at),
        ),
    )
    return cursor.lastrowid


def get_preference_version(conn: sqlite3.Connection, preference_id: str, version: int) -> NotificationPreferenceVersionRecord | None:
    row = conn.execute(
        "SELECT * FROM notification_preference_versions WHERE preference_id = ? AND version = ?", (preference_id, version),
    ).fetchone()
    return _row_to_preference_version(row) if row is not None else None


def get_preference_versions(conn: sqlite3.Connection, preference_id: str) -> list[NotificationPreferenceVersionRecord]:
    rows = conn.execute(
        "SELECT * FROM notification_preference_versions WHERE preference_id = ? ORDER BY version", (preference_id,),
    ).fetchall()
    return [_row_to_preference_version(row) for row in rows]


def get_latest_preference_version(conn: sqlite3.Connection, preference_id: str) -> NotificationPreferenceVersionRecord | None:
    row = conn.execute(
        "SELECT * FROM notification_preference_versions WHERE preference_id = ? ORDER BY version DESC LIMIT 1", (preference_id,),
    ).fetchone()
    return _row_to_preference_version(row) if row is not None else None


def _row_to_preference_version(row: sqlite3.Row) -> NotificationPreferenceVersionRecord:
    return NotificationPreferenceVersionRecord(
        id=row["id"], preference_id=row["preference_id"], version=row["version"],
        enabled_channels=json.loads(row["enabled_channels_json"]), event_types=json.loads(row["event_types_json"]),
        minimum_severity=row["minimum_severity"], minimum_significance=row["minimum_significance"],
        immediate_event_types=json.loads(row["immediate_event_types_json"]),
        digest_event_types=json.loads(row["digest_event_types_json"]), digest_frequency=row["digest_frequency"],
        quiet_hours_start=row["quiet_hours_start"], quiet_hours_end=row["quiet_hours_end"], timezone=row["timezone"],
        max_per_hour=row["max_per_hour"], max_per_day=row["max_per_day"], include_images=bool(row["include_images"]),
        include_original_urls=bool(row["include_original_urls"]),
        include_ranking_explanation=bool(row["include_ranking_explanation"]),
        include_geo_summary=bool(row["include_geo_summary"]),
        include_preference_explanation=bool(row["include_preference_explanation"]),
        include_report_links=bool(row["include_report_links"]), language=row["language"], format=row["format"],
        metadata=json.loads(row["metadata_json"]), created_at=parse_iso(row["created_at"]),
    )


# --------------------------------------------------------------------------- #
# notification_templates (append-only, synced from code)
# --------------------------------------------------------------------------- #


def add_template(conn: sqlite3.Connection, record: NotificationTemplateRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_templates (template_name, version, channel_compatibility_json, description, registered_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (record.template_name, record.version, json.dumps(record.channel_compatibility), record.description, iso(record.registered_at)),
    )
    return cursor.lastrowid


def get_template(conn: sqlite3.Connection, template_name: str, version: int) -> NotificationTemplateRecord | None:
    row = conn.execute(
        "SELECT * FROM notification_templates WHERE template_name = ? AND version = ?", (template_name, version),
    ).fetchone()
    return _row_to_template(row) if row is not None else None


def get_latest_template(conn: sqlite3.Connection, template_name: str) -> NotificationTemplateRecord | None:
    row = conn.execute(
        "SELECT * FROM notification_templates WHERE template_name = ? ORDER BY version DESC LIMIT 1", (template_name,),
    ).fetchone()
    return _row_to_template(row) if row is not None else None


def get_all_templates(conn: sqlite3.Connection) -> list[NotificationTemplateRecord]:
    rows = conn.execute("SELECT * FROM notification_templates ORDER BY template_name, version").fetchall()
    return [_row_to_template(row) for row in rows]


def _row_to_template(row: sqlite3.Row) -> NotificationTemplateRecord:
    return NotificationTemplateRecord(
        id=row["id"], template_name=row["template_name"], version=row["version"],
        channel_compatibility=json.loads(row["channel_compatibility_json"]), description=row["description"],
        registered_at=parse_iso(row["registered_at"]),
    )


# --------------------------------------------------------------------------- #
# notification_batches
# --------------------------------------------------------------------------- #


def add_batch(conn: sqlite3.Connection, record: NotificationBatchRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_batches
            (batch_id, batch_type, started_at, completed_at, deliveries_attempted, deliveries_succeeded,
             deliveries_failed, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.batch_id, record.batch_type, iso(record.started_at),
            iso(record.completed_at) if record.completed_at else None, record.deliveries_attempted,
            record.deliveries_succeeded, record.deliveries_failed, record.notes,
        ),
    )
    return cursor.lastrowid


def update_batch(conn: sqlite3.Connection, record: NotificationBatchRecord) -> None:
    conn.execute(
        """
        UPDATE notification_batches SET
            completed_at = ?, deliveries_attempted = ?, deliveries_succeeded = ?, deliveries_failed = ?, notes = ?
        WHERE batch_id = ?
        """,
        (
            iso(record.completed_at) if record.completed_at else None, record.deliveries_attempted,
            record.deliveries_succeeded, record.deliveries_failed, record.notes, record.batch_id,
        ),
    )


def get_batch(conn: sqlite3.Connection, batch_id: str) -> NotificationBatchRecord | None:
    row = conn.execute("SELECT * FROM notification_batches WHERE batch_id = ?", (batch_id,)).fetchone()
    return _row_to_batch(row) if row is not None else None


def get_all_batches(conn: sqlite3.Connection) -> list[NotificationBatchRecord]:
    rows = conn.execute("SELECT * FROM notification_batches ORDER BY started_at").fetchall()
    return [_row_to_batch(row) for row in rows]


def _row_to_batch(row: sqlite3.Row) -> NotificationBatchRecord:
    return NotificationBatchRecord(
        id=row["id"], batch_id=row["batch_id"], batch_type=row["batch_type"], started_at=parse_iso(row["started_at"]),
        completed_at=parse_iso(row["completed_at"]) if row["completed_at"] else None,
        deliveries_attempted=row["deliveries_attempted"], deliveries_succeeded=row["deliveries_succeeded"],
        deliveries_failed=row["deliveries_failed"], notes=row["notes"],
    )


# --------------------------------------------------------------------------- #
# notification_deliveries
# --------------------------------------------------------------------------- #


def add_delivery(conn: sqlite3.Connection, record: NotificationDeliveryRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_deliveries
            (delivery_id, batch_id, profile_id, saved_search_id, saved_search_version, preference_id,
             preference_version, is_digest, status, channels_json, dedup_key, idempotency_key, created_at,
             next_attempt_at, attempt_count, acknowledged, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.delivery_id, record.batch_id, record.profile_id, record.saved_search_id,
            record.saved_search_version, record.preference_id, record.preference_version, int(record.is_digest),
            record.status, json.dumps(record.channels), record.dedup_key, record.idempotency_key,
            iso(record.created_at), iso(record.next_attempt_at) if record.next_attempt_at else None,
            record.attempt_count, int(record.acknowledged), record.notes,
        ),
    )
    return cursor.lastrowid


def update_delivery(conn: sqlite3.Connection, record: NotificationDeliveryRecord) -> None:
    conn.execute(
        """
        UPDATE notification_deliveries SET
            status = ?, next_attempt_at = ?, attempt_count = ?, notes = ?
        WHERE delivery_id = ?
        """,
        (
            record.status, iso(record.next_attempt_at) if record.next_attempt_at else None, record.attempt_count,
            record.notes, record.delivery_id,
        ),
    )


def acknowledge_delivery(conn: sqlite3.Connection, delivery_id: str) -> None:
    conn.execute("UPDATE notification_deliveries SET acknowledged = 1 WHERE delivery_id = ?", (delivery_id,))


def get_delivery(conn: sqlite3.Connection, delivery_id: str) -> NotificationDeliveryRecord | None:
    row = conn.execute("SELECT * FROM notification_deliveries WHERE delivery_id = ?", (delivery_id,)).fetchone()
    return _row_to_delivery(row) if row is not None else None


def get_delivery_by_idempotency_key(conn: sqlite3.Connection, idempotency_key: str) -> NotificationDeliveryRecord | None:
    row = conn.execute("SELECT * FROM notification_deliveries WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
    return _row_to_delivery(row) if row is not None else None


def get_deliveries_for_profile(conn: sqlite3.Connection, profile_id: str) -> list[NotificationDeliveryRecord]:
    rows = conn.execute(
        "SELECT * FROM notification_deliveries WHERE profile_id = ? ORDER BY created_at", (profile_id,),
    ).fetchall()
    return [_row_to_delivery(row) for row in rows]


def get_deliveries_for_saved_search(conn: sqlite3.Connection, saved_search_id: str) -> list[NotificationDeliveryRecord]:
    rows = conn.execute(
        "SELECT * FROM notification_deliveries WHERE saved_search_id = ? ORDER BY created_at", (saved_search_id,),
    ).fetchall()
    return [_row_to_delivery(row) for row in rows]


def get_deliveries_for_batch(conn: sqlite3.Connection, batch_id: str) -> list[NotificationDeliveryRecord]:
    rows = conn.execute(
        "SELECT * FROM notification_deliveries WHERE batch_id = ? ORDER BY created_at", (batch_id,),
    ).fetchall()
    return [_row_to_delivery(row) for row in rows]


def get_deliveries_by_status(conn: sqlite3.Connection, status: str) -> list[NotificationDeliveryRecord]:
    rows = conn.execute(
        "SELECT * FROM notification_deliveries WHERE status = ? ORDER BY created_at", (status,),
    ).fetchall()
    return [_row_to_delivery(row) for row in rows]


def get_due_retries(conn: sqlite3.Connection, now: datetime) -> list[NotificationDeliveryRecord]:
    """Includes `partially_delivered` alongside `retry_scheduled` — a partial
    success still has failed channels worth retrying ("one channel failure
    does not prevent another channel from succeeding," the mission's own
    words, applies symmetrically to the retry path too).
    """
    rows = conn.execute(
        "SELECT * FROM notification_deliveries WHERE status IN ('retry_scheduled', 'partially_delivered') "
        "AND next_attempt_at IS NOT NULL AND next_attempt_at <= ? ORDER BY next_attempt_at",
        (iso(now),),
    ).fetchall()
    return [_row_to_delivery(row) for row in rows]


def get_latest_digest_delivery_for_preference(conn: sqlite3.Connection, preference_id: str) -> NotificationDeliveryRecord | None:
    row = conn.execute(
        "SELECT * FROM notification_deliveries WHERE preference_id = ? AND is_digest = 1 ORDER BY created_at DESC LIMIT 1",
        (preference_id,),
    ).fetchone()
    return _row_to_delivery(row) if row is not None else None


def get_unacknowledged_deliveries(conn: sqlite3.Connection) -> list[NotificationDeliveryRecord]:
    rows = conn.execute("SELECT * FROM notification_deliveries WHERE acknowledged = 0 ORDER BY created_at").fetchall()
    return [_row_to_delivery(row) for row in rows]


def _row_to_delivery(row: sqlite3.Row) -> NotificationDeliveryRecord:
    return NotificationDeliveryRecord(
        id=row["id"], delivery_id=row["delivery_id"], batch_id=row["batch_id"], profile_id=row["profile_id"],
        saved_search_id=row["saved_search_id"], saved_search_version=row["saved_search_version"],
        preference_id=row["preference_id"], preference_version=row["preference_version"],
        is_digest=bool(row["is_digest"]), status=row["status"], channels=json.loads(row["channels_json"]),
        dedup_key=row["dedup_key"], idempotency_key=row["idempotency_key"], created_at=parse_iso(row["created_at"]),
        next_attempt_at=parse_iso(row["next_attempt_at"]) if row["next_attempt_at"] else None,
        attempt_count=row["attempt_count"], acknowledged=bool(row["acknowledged"]), notes=row["notes"],
    )


# --------------------------------------------------------------------------- #
# notification_delivery_events (append-only link table)
# --------------------------------------------------------------------------- #


def add_delivery_event(conn: sqlite3.Connection, record: NotificationDeliveryEventRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO notification_delivery_events (delivery_id, event_id) VALUES (?, ?)",
        (record.delivery_id, record.event_id),
    )
    return cursor.lastrowid


def get_event_ids_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT event_id FROM notification_delivery_events WHERE delivery_id = ? ORDER BY id", (delivery_id,),
    ).fetchall()
    return [row["event_id"] for row in rows]


def get_delivery_ids_for_event(conn: sqlite3.Connection, event_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT delivery_id FROM notification_delivery_events WHERE event_id = ? ORDER BY id", (event_id,),
    ).fetchall()
    return [row["delivery_id"] for row in rows]


# --------------------------------------------------------------------------- #
# notification_digests (append-only, 1:1 with a digest delivery)
# --------------------------------------------------------------------------- #


def add_digest(conn: sqlite3.Connection, record: NotificationDigestRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO notification_digests (delivery_id, frequency, period_start, period_end, generated_at) VALUES (?, ?, ?, ?, ?)",
        (record.delivery_id, record.frequency, iso(record.period_start), iso(record.period_end), iso(record.generated_at)),
    )
    return cursor.lastrowid


def get_digest_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> NotificationDigestRecord | None:
    row = conn.execute("SELECT * FROM notification_digests WHERE delivery_id = ?", (delivery_id,)).fetchone()
    if row is None:
        return None
    return NotificationDigestRecord(
        id=row["id"], delivery_id=row["delivery_id"], frequency=row["frequency"],
        period_start=parse_iso(row["period_start"]), period_end=parse_iso(row["period_end"]),
        generated_at=parse_iso(row["generated_at"]),
    )


# --------------------------------------------------------------------------- #
# notification_attempts (append-only)
# --------------------------------------------------------------------------- #


def add_attempt(conn: sqlite3.Connection, record: NotificationAttemptRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_attempts
            (delivery_id, channel, attempt_number, status, error, error_category, duration_ms, attempted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.delivery_id, record.channel, record.attempt_number, record.status, record.error,
            record.error_category, record.duration_ms, iso(record.attempted_at),
        ),
    )
    return cursor.lastrowid


def get_attempts_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> list[NotificationAttemptRecord]:
    rows = conn.execute(
        "SELECT * FROM notification_attempts WHERE delivery_id = ? ORDER BY attempted_at", (delivery_id,),
    ).fetchall()
    return [
        NotificationAttemptRecord(
            id=row["id"], delivery_id=row["delivery_id"], channel=row["channel"], attempt_number=row["attempt_number"],
            status=row["status"], attempted_at=parse_iso(row["attempted_at"]), error=row["error"],
            error_category=row["error_category"], duration_ms=row["duration_ms"],
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# notification_messages (append-only)
# --------------------------------------------------------------------------- #


def add_message(conn: sqlite3.Connection, record: NotificationMessageRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO notification_messages
            (delivery_id, channel, subject, body_text, body_html, template_name, template_version, language,
             metadata_json, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.delivery_id, record.channel, record.subject, record.body_text, record.body_html,
            record.template_name, record.template_version, record.language, json.dumps(record.metadata),
            iso(record.generated_at),
        ),
    )
    return cursor.lastrowid


def get_messages_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> list[NotificationMessageRecord]:
    rows = conn.execute(
        "SELECT * FROM notification_messages WHERE delivery_id = ? ORDER BY generated_at", (delivery_id,),
    ).fetchall()
    return [
        NotificationMessageRecord(
            id=row["id"], delivery_id=row["delivery_id"], channel=row["channel"], subject=row["subject"],
            body_text=row["body_text"], body_html=row["body_html"], template_name=row["template_name"],
            template_version=row["template_version"], language=row["language"],
            metadata=json.loads(row["metadata_json"]), generated_at=parse_iso(row["generated_at"]),
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# rate_limit_observations (append-only)
# --------------------------------------------------------------------------- #


def add_rate_limit_observation(conn: sqlite3.Connection, record: RateLimitObservationRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO rate_limit_observations (profile_id, channel, occurred_at) VALUES (?, ?, ?)",
        (record.profile_id, record.channel, iso(record.occurred_at)),
    )
    return cursor.lastrowid


def count_rate_limit_observations_since(conn: sqlite3.Connection, profile_id: str, channel: str, since: datetime) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM rate_limit_observations WHERE profile_id = ? AND channel = ? AND occurred_at >= ?",
        (profile_id, channel, iso(since)),
    ).fetchone()
    return row["n"] if row else 0


# --------------------------------------------------------------------------- #
# channel_health_observations (append-only)
# --------------------------------------------------------------------------- #


def add_channel_health_observation(conn: sqlite3.Connection, record: ChannelHealthObservationRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO channel_health_observations (channel, succeeded, error, duration_ms, observed_at) VALUES (?, ?, ?, ?, ?)",
        (record.channel, int(record.succeeded), record.error, record.duration_ms, iso(record.observed_at)),
    )
    return cursor.lastrowid


def get_recent_channel_observations(conn: sqlite3.Connection, channel: str, *, limit: int = 20) -> list[ChannelHealthObservationRecord]:
    rows = conn.execute(
        "SELECT * FROM channel_health_observations WHERE channel = ? ORDER BY observed_at DESC LIMIT ?", (channel, limit),
    ).fetchall()
    return [
        ChannelHealthObservationRecord(
            id=row["id"], channel=row["channel"], succeeded=bool(row["succeeded"]), error=row["error"],
            duration_ms=row["duration_ms"], observed_at=parse_iso(row["observed_at"]),
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# notification_acknowledgements (append-only)
# --------------------------------------------------------------------------- #


def add_acknowledgement(conn: sqlite3.Connection, record: NotificationAcknowledgementRecord) -> int:
    cursor = conn.execute(
        "INSERT INTO notification_acknowledgements (delivery_id, acknowledged_at, acknowledged_by, note) VALUES (?, ?, ?, ?)",
        (record.delivery_id, iso(record.acknowledged_at), record.acknowledged_by, record.note),
    )
    return cursor.lastrowid


def get_acknowledgements_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> list[NotificationAcknowledgementRecord]:
    rows = conn.execute(
        "SELECT * FROM notification_acknowledgements WHERE delivery_id = ? ORDER BY acknowledged_at", (delivery_id,),
    ).fetchall()
    return [
        NotificationAcknowledgementRecord(
            id=row["id"], delivery_id=row["delivery_id"], acknowledged_at=parse_iso(row["acknowledged_at"]),
            acknowledged_by=row["acknowledged_by"], note=row["note"],
        )
        for row in rows
    ]
