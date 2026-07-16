"""`NotificationService` — thin read/write orchestration over
`storage.notification_repository`, mirroring `monitoring/service.py`'s own
shape: plain functions, no business logic, only translation between this
package's domain dataclasses (`src.notifications.models`) and the storage
layer's row-shaped ones (`src.storage.models`). Deciding *when*/*what*/*why*
to record stays `NotificationEngine`'s job.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.notifications.models import (
    NotificationAttempt,
    NotificationBatch,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationDigest,
    NotificationHealth,
    NotificationMessage,
    NotificationPreference,
    NotificationPreferenceVersion,
)
from src.storage import notification_repository as repo
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


# --------------------------------------------------------------------------- #
# preferences + versions
# --------------------------------------------------------------------------- #


def record_preference(conn: sqlite3.Connection, preference: NotificationPreference) -> int:
    return repo.add_preference(conn, _preference_to_record(preference))


def update_preference(conn: sqlite3.Connection, preference: NotificationPreference) -> None:
    repo.update_preference_metadata(conn, _preference_to_record(preference))


def get_preference(conn: sqlite3.Connection, preference_id: str) -> NotificationPreference | None:
    record = repo.get_preference(conn, preference_id)
    return _preference_from_record(record) if record is not None else None


def get_all_preferences(conn: sqlite3.Connection, *, profile_id: str | None = None, enabled_only: bool = False) -> list[NotificationPreference]:
    return [_preference_from_record(r) for r in repo.get_all_preferences(conn, profile_id=profile_id, enabled_only=enabled_only)]


def _preference_to_record(preference: NotificationPreference) -> NotificationPreferenceRecord:
    return NotificationPreferenceRecord(
        preference_id=preference.preference_id, profile_id=preference.profile_id,
        current_version=preference.current_version, enabled=preference.enabled, created_at=preference.created_at,
        updated_at=preference.updated_at, saved_search_id=preference.saved_search_id, id=preference.id,
    )


def _preference_from_record(record: NotificationPreferenceRecord) -> NotificationPreference:
    return NotificationPreference(
        preference_id=record.preference_id, profile_id=record.profile_id, current_version=record.current_version,
        enabled=record.enabled, created_at=record.created_at, updated_at=record.updated_at,
        saved_search_id=record.saved_search_id, id=record.id,
    )


def record_preference_version(conn: sqlite3.Connection, version: NotificationPreferenceVersion) -> int:
    return repo.add_preference_version(conn, _version_to_record(version))


def get_preference_version(conn: sqlite3.Connection, preference_id: str, version: int) -> NotificationPreferenceVersion | None:
    record = repo.get_preference_version(conn, preference_id, version)
    return _version_from_record(record) if record is not None else None


def get_latest_preference_version(conn: sqlite3.Connection, preference_id: str) -> NotificationPreferenceVersion | None:
    record = repo.get_latest_preference_version(conn, preference_id)
    return _version_from_record(record) if record is not None else None


def get_preference_versions(conn: sqlite3.Connection, preference_id: str) -> list[NotificationPreferenceVersion]:
    return [_version_from_record(r) for r in repo.get_preference_versions(conn, preference_id)]


def _version_to_record(version: NotificationPreferenceVersion) -> NotificationPreferenceVersionRecord:
    return NotificationPreferenceVersionRecord(
        preference_id=version.preference_id, version=version.version, enabled_channels=version.enabled_channels,
        event_types=version.event_types, minimum_severity=version.minimum_severity,
        minimum_significance=version.minimum_significance, immediate_event_types=version.immediate_event_types,
        digest_event_types=version.digest_event_types, digest_frequency=version.digest_frequency,
        quiet_hours_start=version.quiet_hours_start, quiet_hours_end=version.quiet_hours_end,
        timezone=version.timezone, max_per_hour=version.max_per_hour, max_per_day=version.max_per_day,
        include_images=version.include_images, include_original_urls=version.include_original_urls,
        include_ranking_explanation=version.include_ranking_explanation, include_geo_summary=version.include_geo_summary,
        include_preference_explanation=version.include_preference_explanation, include_report_links=version.include_report_links,
        language=version.language, format=version.format, metadata=version.metadata, created_at=version.created_at,
        id=version.id,
    )


def _version_from_record(record: NotificationPreferenceVersionRecord) -> NotificationPreferenceVersion:
    return NotificationPreferenceVersion(
        preference_id=record.preference_id, version=record.version, enabled_channels=record.enabled_channels,
        event_types=record.event_types, immediate_event_types=record.immediate_event_types,
        digest_event_types=record.digest_event_types, timezone=record.timezone, include_images=record.include_images,
        include_original_urls=record.include_original_urls, include_ranking_explanation=record.include_ranking_explanation,
        include_geo_summary=record.include_geo_summary, include_preference_explanation=record.include_preference_explanation,
        include_report_links=record.include_report_links, language=record.language, format=record.format,
        metadata=record.metadata, created_at=record.created_at, minimum_severity=record.minimum_severity,
        minimum_significance=record.minimum_significance, digest_frequency=record.digest_frequency,
        quiet_hours_start=record.quiet_hours_start, quiet_hours_end=record.quiet_hours_end,
        max_per_hour=record.max_per_hour, max_per_day=record.max_per_day, id=record.id,
    )


# --------------------------------------------------------------------------- #
# templates (metadata sync only — rendering logic lives in code)
# --------------------------------------------------------------------------- #


def sync_template(conn: sqlite3.Connection, template_name: str, version: int, channel_compatibility: list[str], description: str, now: datetime) -> None:
    """Idempotent: only inserts a new `notification_templates` row when this
    exact (name, version) pair isn't already recorded — mirrors
    `filter_engine.sync_filter_definitions()`'s own "sync metadata from code"
    pattern.
    """
    if repo.get_template(conn, template_name, version) is not None:
        return
    repo.add_template(conn, NotificationTemplateRecord(
        template_name=template_name, version=version, channel_compatibility=channel_compatibility,
        description=description, registered_at=now,
    ))


def get_all_templates(conn: sqlite3.Connection) -> list[NotificationTemplateRecord]:
    return repo.get_all_templates(conn)


def sync_registered_templates(conn: sqlite3.Connection, now: datetime) -> None:
    """Syncs every self-registered `NotificationTemplate`'s metadata into
    `notification_templates` — mirrors `filter_engine.sync_filter_definitions()`'s
    own "sync from code, not from user input" pattern. Idempotent — safe to
    call at the start of every `NotificationEngine` batch.
    """
    from src.notifications.template_registry import NotificationTemplateRegistry

    for template in NotificationTemplateRegistry.all():
        sync_template(conn, template.template_name, template.version, list(template.channel_compatibility), template.__class__.__doc__ or template.template_name, now)


# --------------------------------------------------------------------------- #
# batches
# --------------------------------------------------------------------------- #


def record_batch(conn: sqlite3.Connection, batch: NotificationBatch) -> int:
    return repo.add_batch(conn, _batch_to_record(batch))


def update_batch(conn: sqlite3.Connection, batch: NotificationBatch) -> None:
    repo.update_batch(conn, _batch_to_record(batch))


def get_batch(conn: sqlite3.Connection, batch_id: str) -> NotificationBatch | None:
    record = repo.get_batch(conn, batch_id)
    return _batch_from_record(record) if record is not None else None


def get_all_batches(conn: sqlite3.Connection) -> list[NotificationBatch]:
    return [_batch_from_record(r) for r in repo.get_all_batches(conn)]


def _batch_to_record(batch: NotificationBatch) -> NotificationBatchRecord:
    return NotificationBatchRecord(
        batch_id=batch.batch_id, batch_type=batch.batch_type, started_at=batch.started_at,
        completed_at=batch.completed_at, deliveries_attempted=batch.deliveries_attempted,
        deliveries_succeeded=batch.deliveries_succeeded, deliveries_failed=batch.deliveries_failed,
        notes=batch.notes, id=batch.id,
    )


def _batch_from_record(record: NotificationBatchRecord) -> NotificationBatch:
    return NotificationBatch(
        batch_type=record.batch_type, started_at=record.started_at, completed_at=record.completed_at,
        deliveries_attempted=record.deliveries_attempted, deliveries_succeeded=record.deliveries_succeeded,
        deliveries_failed=record.deliveries_failed, notes=record.notes, batch_id=record.batch_id, id=record.id,
    )


# --------------------------------------------------------------------------- #
# deliveries + delivery-event links
# --------------------------------------------------------------------------- #


def record_delivery(conn: sqlite3.Connection, delivery: NotificationDelivery) -> int:
    row_id = repo.add_delivery(conn, _delivery_to_record(delivery))
    for event_id in delivery.event_ids:
        repo.add_delivery_event(conn, NotificationDeliveryEventRecord(delivery_id=delivery.delivery_id, event_id=event_id))
    return row_id


def update_delivery(conn: sqlite3.Connection, delivery: NotificationDelivery) -> None:
    repo.update_delivery(conn, _delivery_to_record(delivery))


def acknowledge_delivery(conn: sqlite3.Connection, delivery_id: str, *, acknowledged_by: str | None = None, note: str | None = None, now: datetime) -> None:
    repo.acknowledge_delivery(conn, delivery_id)
    repo.add_acknowledgement(conn, NotificationAcknowledgementRecord(delivery_id=delivery_id, acknowledged_at=now, acknowledged_by=acknowledged_by, note=note))


def get_acknowledgements_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> list[NotificationAcknowledgementRecord]:
    """Append-only audit trail — acknowledging never deletes a prior
    acknowledgement, even a re-acknowledgement records a second row.
    """
    return repo.get_acknowledgements_for_delivery(conn, delivery_id)


def get_delivery(conn: sqlite3.Connection, delivery_id: str) -> NotificationDelivery | None:
    record = repo.get_delivery(conn, delivery_id)
    if record is None:
        return None
    return _delivery_from_record(conn, record)


def get_delivery_by_idempotency_key(conn: sqlite3.Connection, idempotency_key: str) -> NotificationDelivery | None:
    record = repo.get_delivery_by_idempotency_key(conn, idempotency_key)
    return _delivery_from_record(conn, record) if record is not None else None


def get_deliveries_for_profile(conn: sqlite3.Connection, profile_id: str) -> list[NotificationDelivery]:
    return [_delivery_from_record(conn, r) for r in repo.get_deliveries_for_profile(conn, profile_id)]


def get_deliveries_for_saved_search(conn: sqlite3.Connection, saved_search_id: str) -> list[NotificationDelivery]:
    return [_delivery_from_record(conn, r) for r in repo.get_deliveries_for_saved_search(conn, saved_search_id)]


def get_deliveries_for_batch(conn: sqlite3.Connection, batch_id: str) -> list[NotificationDelivery]:
    return [_delivery_from_record(conn, r) for r in repo.get_deliveries_for_batch(conn, batch_id)]


def get_deliveries_by_status(conn: sqlite3.Connection, status: str) -> list[NotificationDelivery]:
    return [_delivery_from_record(conn, r) for r in repo.get_deliveries_by_status(conn, status)]


def get_due_retries(conn: sqlite3.Connection, now: datetime) -> list[NotificationDelivery]:
    return [_delivery_from_record(conn, r) for r in repo.get_due_retries(conn, now)]


def get_unacknowledged_deliveries(conn: sqlite3.Connection) -> list[NotificationDelivery]:
    return [_delivery_from_record(conn, r) for r in repo.get_unacknowledged_deliveries(conn)]


def get_event_ids_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> list[str]:
    return repo.get_event_ids_for_delivery(conn, delivery_id)


def get_delivery_ids_for_event(conn: sqlite3.Connection, event_id: str) -> list[str]:
    return repo.get_delivery_ids_for_event(conn, event_id)


def _delivery_to_record(delivery: NotificationDelivery) -> NotificationDeliveryRecord:
    return NotificationDeliveryRecord(
        delivery_id=delivery.delivery_id, batch_id=delivery.batch_id, profile_id=delivery.profile_id,
        saved_search_id=delivery.saved_search_id, saved_search_version=delivery.saved_search_version,
        preference_id=delivery.preference_id, preference_version=delivery.preference_version,
        is_digest=delivery.is_digest, status=delivery.status.value, channels=delivery.channels,
        dedup_key=delivery.dedup_key, idempotency_key=delivery.idempotency_key, created_at=delivery.created_at,
        next_attempt_at=delivery.next_attempt_at, attempt_count=delivery.attempt_count,
        acknowledged=delivery.acknowledged, notes=delivery.notes, id=delivery.id,
    )


def _delivery_from_record(conn: sqlite3.Connection, record: NotificationDeliveryRecord) -> NotificationDelivery:
    return NotificationDelivery(
        profile_id=record.profile_id, preference_id=record.preference_id, preference_version=record.preference_version,
        is_digest=record.is_digest, status=NotificationDeliveryStatus(record.status), channels=record.channels,
        event_ids=repo.get_event_ids_for_delivery(conn, record.delivery_id), dedup_key=record.dedup_key,
        idempotency_key=record.idempotency_key, created_at=record.created_at, batch_id=record.batch_id,
        saved_search_id=record.saved_search_id, saved_search_version=record.saved_search_version,
        next_attempt_at=record.next_attempt_at, attempt_count=record.attempt_count, acknowledged=record.acknowledged,
        notes=record.notes, delivery_id=record.delivery_id, id=record.id,
    )


# --------------------------------------------------------------------------- #
# digests
# --------------------------------------------------------------------------- #


def record_digest(conn: sqlite3.Connection, digest: NotificationDigest) -> int:
    return repo.add_digest(conn, NotificationDigestRecord(
        delivery_id=digest.delivery_id, frequency=digest.frequency, period_start=digest.period_start,
        period_end=digest.period_end, generated_at=digest.generated_at,
    ))


def get_latest_digest_for_preference(conn: sqlite3.Connection, preference_id: str) -> NotificationDigest | None:
    delivery_record = repo.get_latest_digest_delivery_for_preference(conn, preference_id)
    if delivery_record is None:
        return None
    return get_digest_for_delivery(conn, delivery_record.delivery_id)


def get_digest_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> NotificationDigest | None:
    record = repo.get_digest_for_delivery(conn, delivery_id)
    if record is None:
        return None
    return NotificationDigest(
        delivery_id=record.delivery_id, frequency=record.frequency, period_start=record.period_start,
        period_end=record.period_end, event_ids=repo.get_event_ids_for_delivery(conn, delivery_id),
        generated_at=record.generated_at,
    )


# --------------------------------------------------------------------------- #
# attempts
# --------------------------------------------------------------------------- #


def record_attempt(conn: sqlite3.Connection, attempt: NotificationAttempt) -> int:
    return repo.add_attempt(conn, NotificationAttemptRecord(
        delivery_id=attempt.delivery_id, channel=attempt.channel, attempt_number=attempt.attempt_number,
        status=attempt.status, attempted_at=attempt.attempted_at, error=attempt.error,
        error_category=attempt.error_category, duration_ms=attempt.duration_ms,
    ))


def get_attempts_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> list[NotificationAttempt]:
    return [
        NotificationAttempt(
            delivery_id=r.delivery_id, channel=r.channel, attempt_number=r.attempt_number, status=r.status,
            attempted_at=r.attempted_at, error=r.error, error_category=r.error_category, duration_ms=r.duration_ms, id=r.id,
        )
        for r in repo.get_attempts_for_delivery(conn, delivery_id)
    ]


# --------------------------------------------------------------------------- #
# messages
# --------------------------------------------------------------------------- #


def record_message(conn: sqlite3.Connection, message: NotificationMessage) -> int:
    return repo.add_message(conn, NotificationMessageRecord(
        delivery_id=message.delivery_id, channel=message.channel, subject=message.subject,
        body_text=message.body_text, body_html=message.body_html, template_name=message.template_name,
        template_version=message.template_version, language=message.language,
        metadata={
            "event_ids": message.event_ids, "original_listing_urls": message.original_listing_urls,
            "report_links": message.report_links, "attachments": message.attachments, **message.metadata,
        },
        generated_at=message.generated_at,
    ))


def get_messages_for_delivery(conn: sqlite3.Connection, delivery_id: str) -> list[NotificationMessageRecord]:
    return repo.get_messages_for_delivery(conn, delivery_id)


# --------------------------------------------------------------------------- #
# rate limiting + channel health
# --------------------------------------------------------------------------- #


def record_rate_limit_observation(conn: sqlite3.Connection, profile_id: str, channel: str, occurred_at: datetime) -> int:
    return repo.add_rate_limit_observation(conn, RateLimitObservationRecord(profile_id=profile_id, channel=channel, occurred_at=occurred_at))


def count_rate_limit_observations_since(conn: sqlite3.Connection, profile_id: str, channel: str, since: datetime) -> int:
    return repo.count_rate_limit_observations_since(conn, profile_id, channel, since)


def record_channel_health_observation(conn: sqlite3.Connection, channel: str, succeeded: bool, observed_at: datetime, *, error: str | None = None, duration_ms: int | None = None) -> int:
    return repo.add_channel_health_observation(conn, ChannelHealthObservationRecord(
        channel=channel, succeeded=succeeded, error=error, duration_ms=duration_ms, observed_at=observed_at,
    ))


def compute_channel_health(conn: sqlite3.Connection, channel: str, *, window: int = 20) -> NotificationHealth:
    observations = repo.get_recent_channel_observations(conn, channel, limit=window)
    successes = [o for o in observations if o.succeeded]
    failures = [o for o in observations if not o.succeeded]
    return NotificationHealth(
        channel=channel, recent_success_count=len(successes), recent_failure_count=len(failures),
        last_success_at=successes[0].observed_at if successes else None,
        last_failure_at=failures[0].observed_at if failures else None,
    )
