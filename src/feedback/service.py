"""`FeedbackService` — thin read/write orchestration over `storage.feedback_repository`,
mirroring `knowledge_service.py`/`search_memory_service.py`'s own shape: plain
functions, no business logic, only translation between this package's domain
dataclasses and the storage layer's row-shaped ones. Deciding *when*/*what*/*why*
to record stays `FeedbackEngine`'s job.
"""

from __future__ import annotations

import sqlite3

from datetime import datetime

from src.feedback.models import FeedbackEvent, PreferenceAdjustment, PreferenceObservation
from src.storage import feedback_repository
from src.storage.models import (
    FeedbackEventRecord,
    PreferenceAdjustmentRecord,
    PreferenceObservationRecord,
    PreferenceSnapshotRecord,
)


def record_event(conn: sqlite3.Connection, event: FeedbackEvent) -> None:
    feedback_repository.add_event(
        conn,
        FeedbackEventRecord(
            event_id=event.event_id, profile_id=event.profile_id, search_id=event.search_id,
            apartment_id=event.apartment_id, event_type=event.event_type, event_value=event.event_value,
            occurred_at=event.occurred_at, source=event.source, session_id=event.session_id,
            metadata=event.metadata, ranking_profile=event.ranking_profile, search_filters=event.search_filters,
        ),
    )


def get_events_for_profile(conn: sqlite3.Connection, profile_id: str) -> list[FeedbackEvent]:
    return [_event_from_record(r) for r in feedback_repository.get_events_for_profile(conn, profile_id)]


def get_events_for_apartment(conn: sqlite3.Connection, apartment_id: str) -> list[FeedbackEvent]:
    return [_event_from_record(r) for r in feedback_repository.get_events_for_apartment(conn, apartment_id)]


def _event_from_record(record: FeedbackEventRecord) -> FeedbackEvent:
    return FeedbackEvent(
        profile_id=record.profile_id, event_type=record.event_type, occurred_at=record.occurred_at,
        source=record.source, event_value=record.event_value, metadata=record.metadata,
        search_id=record.search_id, apartment_id=record.apartment_id, session_id=record.session_id,
        ranking_profile=record.ranking_profile, search_filters=record.search_filters, event_id=record.event_id,
    )


def record_observation(conn: sqlite3.Connection, observation: PreferenceObservation) -> None:
    feedback_repository.add_observation(
        conn,
        PreferenceObservationRecord(
            profile_id=observation.profile_id, preference_key=observation.preference_key,
            event_id=observation.event_id, direction=observation.direction, magnitude=observation.magnitude,
            source_type=observation.source_type, computed_at=observation.computed_at,
            explanation=observation.explanation, observed_value=observation.observed_value,
        ),
    )


def get_observations(conn: sqlite3.Connection, profile_id: str, preference_key: str) -> list[PreferenceObservation]:
    return [_observation_from_record(r) for r in feedback_repository.get_observations(conn, profile_id, preference_key)]


def get_all_observations(conn: sqlite3.Connection, profile_id: str) -> list[PreferenceObservation]:
    return [_observation_from_record(r) for r in feedback_repository.get_all_observations_for_profile(conn, profile_id)]


def _observation_from_record(record: PreferenceObservationRecord) -> PreferenceObservation:
    return PreferenceObservation(
        profile_id=record.profile_id, preference_key=record.preference_key, event_id=record.event_id,
        direction=record.direction, magnitude=record.magnitude, source_type=record.source_type,
        computed_at=record.computed_at, explanation=record.explanation, observed_value=record.observed_value,
    )


def record_adjustment(conn: sqlite3.Connection, adjustment: PreferenceAdjustment) -> int:
    new_id = feedback_repository.add_adjustment(
        conn,
        PreferenceAdjustmentRecord(
            profile_id=adjustment.profile_id, preference_key=adjustment.preference_key,
            previous_value=adjustment.previous_value, new_value=adjustment.new_value,
            previous_confidence=adjustment.previous_confidence, new_confidence=adjustment.new_confidence,
            reason=adjustment.reason, triggered_by_event_ids=adjustment.triggered_by_event_ids,
            adjustment_type=adjustment.adjustment_type, reverses_adjustment_id=adjustment.reverses_adjustment_id,
            applied_at=adjustment.applied_at,
        ),
    )
    return new_id


def get_adjustments(conn: sqlite3.Connection, profile_id: str, preference_key: str) -> list[PreferenceAdjustment]:
    return [_adjustment_from_record(r) for r in feedback_repository.get_adjustments(conn, profile_id, preference_key)]


def get_adjustment_by_id(conn: sqlite3.Connection, adjustment_id: int) -> PreferenceAdjustment | None:
    record = feedback_repository.get_adjustment_by_id(conn, adjustment_id)
    return _adjustment_from_record(record) if record is not None else None


def _adjustment_from_record(record: PreferenceAdjustmentRecord) -> PreferenceAdjustment:
    return PreferenceAdjustment(
        profile_id=record.profile_id, preference_key=record.preference_key, reason=record.reason,
        triggered_by_event_ids=record.triggered_by_event_ids, adjustment_type=record.adjustment_type,
        applied_at=record.applied_at, previous_value=record.previous_value, new_value=record.new_value,
        previous_confidence=record.previous_confidence, new_confidence=record.new_confidence,
        reverses_adjustment_id=record.reverses_adjustment_id, id=record.id,
    )


def record_snapshot(conn: sqlite3.Connection, profile_id: str, snapshot: dict, reason: str, created_at: datetime) -> None:
    feedback_repository.add_snapshot(
        conn, PreferenceSnapshotRecord(profile_id=profile_id, snapshot=snapshot, reason=reason, created_at=created_at)
    )


def get_snapshots(conn: sqlite3.Connection, profile_id: str) -> list[PreferenceSnapshotRecord]:
    return feedback_repository.get_snapshots(conn, profile_id)
