"""`MonitoringService` — thin read/write orchestration over
`storage.monitoring_repository`, mirroring `discovery/automatic/service.py`'s
own shape: plain functions, no business logic, only translation between this
package's domain dataclasses (`src.monitoring.models`) and the storage layer's
row-shaped ones (`src.storage.models`). Deciding *when*/*what*/*why* to record
stays `MonitoringEngine`'s job.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.monitoring.models import (
    MonitoringEvent,
    MonitoringPolicy,
    MonitoringRun,
    MonitoringRunStatus,
    MonitoringSchedule,
    MonitoringStatistics,
    SavedSearch,
    SavedSearchVersion,
)
from src.storage import monitoring_repository
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


# --------------------------------------------------------------------------- #
# saved searches + versions
# --------------------------------------------------------------------------- #


def record_saved_search(conn: sqlite3.Connection, saved_search: SavedSearch) -> int:
    return monitoring_repository.add_saved_search(conn, _saved_search_to_record(saved_search))


def update_saved_search(conn: sqlite3.Connection, saved_search: SavedSearch) -> None:
    monitoring_repository.update_saved_search_metadata(conn, _saved_search_to_record(saved_search))


def get_saved_search(conn: sqlite3.Connection, saved_search_id: str) -> SavedSearch | None:
    record = monitoring_repository.get_saved_search(conn, saved_search_id)
    return _saved_search_from_record(record) if record is not None else None


def get_all_saved_searches(conn: sqlite3.Connection, *, enabled_only: bool = False) -> list[SavedSearch]:
    return [_saved_search_from_record(r) for r in monitoring_repository.get_all_saved_searches(conn, enabled_only=enabled_only)]


def _saved_search_to_record(saved_search: SavedSearch) -> SavedSearchRecord:
    return SavedSearchRecord(
        saved_search_id=saved_search.saved_search_id, name=saved_search.name,
        current_version=saved_search.current_version, enabled=saved_search.enabled,
        created_at=saved_search.created_at, updated_at=saved_search.updated_at,
        profile_id=saved_search.profile_id, description=saved_search.description, id=saved_search.id,
    )


def _saved_search_from_record(record: SavedSearchRecord) -> SavedSearch:
    return SavedSearch(
        saved_search_id=record.saved_search_id, name=record.name, current_version=record.current_version,
        enabled=record.enabled, created_at=record.created_at, updated_at=record.updated_at,
        profile_id=record.profile_id, description=record.description, id=record.id,
    )


def record_saved_search_version(conn: sqlite3.Connection, version: SavedSearchVersion) -> int:
    return monitoring_repository.add_saved_search_version(conn, _version_to_record(version))


def get_saved_search_version(conn: sqlite3.Connection, saved_search_id: str, version: int) -> SavedSearchVersion | None:
    record = monitoring_repository.get_saved_search_version(conn, saved_search_id, version)
    return _version_from_record(record) if record is not None else None


def get_saved_search_versions(conn: sqlite3.Connection, saved_search_id: str) -> list[SavedSearchVersion]:
    return [_version_from_record(r) for r in monitoring_repository.get_saved_search_versions(conn, saved_search_id)]


def get_latest_saved_search_version(conn: sqlite3.Connection, saved_search_id: str) -> SavedSearchVersion | None:
    record = monitoring_repository.get_latest_saved_search_version(conn, saved_search_id)
    return _version_from_record(record) if record is not None else None


def _version_to_record(version: SavedSearchVersion) -> SavedSearchVersionRecord:
    return SavedSearchVersionRecord(
        saved_search_id=version.saved_search_id, version=version.version, request=version.request,
        active_filters=version.active_filters, selected_platforms=version.selected_platforms,
        selected_connectors=version.selected_connectors, geographic_destinations=version.geographic_destinations,
        monitoring_policy=version.monitoring_policy.as_dict(), report_options=version.report_options,
        retention_policy=version.retention_policy, tags=version.tags, metadata=version.metadata,
        created_at=version.created_at, ranking_profile=version.ranking_profile, feedback_mode=version.feedback_mode,
        id=version.id,
    )


def _version_from_record(record: SavedSearchVersionRecord) -> SavedSearchVersion:
    return SavedSearchVersion(
        saved_search_id=record.saved_search_id, version=record.version, request=record.request,
        active_filters=record.active_filters, selected_platforms=record.selected_platforms,
        selected_connectors=record.selected_connectors, geographic_destinations=record.geographic_destinations,
        monitoring_policy=MonitoringPolicy.from_dict(record.monitoring_policy), report_options=record.report_options,
        retention_policy=record.retention_policy, tags=record.tags, metadata=record.metadata,
        created_at=record.created_at, ranking_profile=record.ranking_profile, feedback_mode=record.feedback_mode,
        id=record.id,
    )


# --------------------------------------------------------------------------- #
# schedules
# --------------------------------------------------------------------------- #


def record_schedule(conn: sqlite3.Connection, schedule: MonitoringSchedule) -> int:
    return monitoring_repository.add_schedule(conn, _schedule_to_record(schedule))


def update_schedule(conn: sqlite3.Connection, schedule: MonitoringSchedule) -> None:
    monitoring_repository.update_schedule(conn, _schedule_to_record(schedule))


def get_schedule(conn: sqlite3.Connection, saved_search_id: str) -> MonitoringSchedule | None:
    record = monitoring_repository.get_schedule(conn, saved_search_id)
    return _schedule_from_record(record) if record is not None else None


def get_due_schedules(conn: sqlite3.Connection, now: datetime) -> list[MonitoringSchedule]:
    return [_schedule_from_record(r) for r in monitoring_repository.get_due_schedules(conn, now)]


def claim_due_run(conn: sqlite3.Connection, saved_search_id: str, claimed_by: str, claimed_at: datetime, claim_expires_at: datetime) -> bool:
    return monitoring_repository.claim_due_run(conn, saved_search_id, claimed_by, claimed_at, claim_expires_at)


def release_run_claim(conn: sqlite3.Connection, saved_search_id: str) -> None:
    monitoring_repository.release_run_claim(conn, saved_search_id)


def _schedule_to_record(schedule: MonitoringSchedule) -> MonitoringScheduleRecord:
    return MonitoringScheduleRecord(
        saved_search_id=schedule.saved_search_id, next_run_at=schedule.next_run_at, last_run_at=schedule.last_run_at,
        last_run_status=schedule.last_run_status, claimed_by=schedule.claimed_by, claimed_at=schedule.claimed_at,
        claim_expires_at=schedule.claim_expires_at,
    )


def _schedule_from_record(record: MonitoringScheduleRecord) -> MonitoringSchedule:
    return MonitoringSchedule(
        saved_search_id=record.saved_search_id, next_run_at=record.next_run_at, last_run_at=record.last_run_at,
        last_run_status=record.last_run_status, claimed_by=record.claimed_by, claimed_at=record.claimed_at,
        claim_expires_at=record.claim_expires_at,
    )


# --------------------------------------------------------------------------- #
# monitoring runs
# --------------------------------------------------------------------------- #


def record_run(conn: sqlite3.Connection, run: MonitoringRun) -> int:
    return monitoring_repository.add_run(conn, _run_to_record(run))


def update_run(conn: sqlite3.Connection, run: MonitoringRun) -> None:
    monitoring_repository.update_run_status(conn, run.monitoring_run_id, _run_to_record(run))


def get_run(conn: sqlite3.Connection, monitoring_run_id: str) -> MonitoringRun | None:
    record = monitoring_repository.get_run(conn, monitoring_run_id)
    return _run_from_record(record) if record is not None else None


def get_runs_for_saved_search(conn: sqlite3.Connection, saved_search_id: str) -> list[MonitoringRun]:
    return [_run_from_record(r) for r in monitoring_repository.get_runs_for_saved_search(conn, saved_search_id)]


def get_latest_run_for_saved_search(conn: sqlite3.Connection, saved_search_id: str) -> MonitoringRun | None:
    record = monitoring_repository.get_latest_run_for_saved_search(conn, saved_search_id)
    return _run_from_record(record) if record is not None else None


def get_all_runs(conn: sqlite3.Connection) -> list[MonitoringRun]:
    return [_run_from_record(r) for r in monitoring_repository.get_all_runs(conn)]


def _run_to_record(run: MonitoringRun) -> MonitoringRunRecord:
    return MonitoringRunRecord(
        monitoring_run_id=run.monitoring_run_id, saved_search_id=run.saved_search_id,
        saved_search_version=run.saved_search_version, status=run.status.value, started_at=run.started_at,
        platforms_attempted=run.platforms_attempted, platforms_succeeded=run.platforms_succeeded,
        platforms_failed=run.platforms_failed, search_id=run.search_id, completed_at=run.completed_at,
        event_count=run.event_count, notes=run.notes, id=run.id,
    )


def _run_from_record(record: MonitoringRunRecord) -> MonitoringRun:
    return MonitoringRun(
        saved_search_id=record.saved_search_id, saved_search_version=record.saved_search_version,
        started_at=record.started_at, status=MonitoringRunStatus(record.status), search_id=record.search_id,
        completed_at=record.completed_at, platforms_attempted=record.platforms_attempted,
        platforms_succeeded=record.platforms_succeeded, platforms_failed=record.platforms_failed,
        event_count=record.event_count, notes=record.notes, monitoring_run_id=record.monitoring_run_id, id=record.id,
    )


# --------------------------------------------------------------------------- #
# events
# --------------------------------------------------------------------------- #


def record_event(conn: sqlite3.Connection, event: MonitoringEvent) -> int:
    return monitoring_repository.add_event(conn, _event_to_record(event))


def acknowledge_event(conn: sqlite3.Connection, event_id: str, *, acknowledged_by: str | None = None, note: str | None = None, now: datetime) -> None:
    monitoring_repository.acknowledge_event(conn, event_id)
    monitoring_repository.add_acknowledgement(
        conn, EventAcknowledgementRecord(event_id=event_id, acknowledged_at=now, acknowledged_by=acknowledged_by, note=note),
    )


def get_event(conn: sqlite3.Connection, event_id: str) -> MonitoringEvent | None:
    record = monitoring_repository.get_event(conn, event_id)
    return _event_from_record(record) if record is not None else None


def get_events_for_run(conn: sqlite3.Connection, monitoring_run_id: str) -> list[MonitoringEvent]:
    return [_event_from_record(r) for r in monitoring_repository.get_events_for_run(conn, monitoring_run_id)]


def get_events_for_saved_search(
    conn: sqlite3.Connection, saved_search_id: str, *, event_type: str | None = None, severity: str | None = None,
) -> list[MonitoringEvent]:
    return [
        _event_from_record(r)
        for r in monitoring_repository.get_events_for_saved_search(conn, saved_search_id, event_type=event_type, severity=severity)
    ]


def get_events_by_dedup_key(conn: sqlite3.Connection, dedup_key: str) -> list[MonitoringEvent]:
    return [_event_from_record(r) for r in monitoring_repository.get_events_by_dedup_key(conn, dedup_key)]


def get_unacknowledged_events(conn: sqlite3.Connection) -> list[MonitoringEvent]:
    return [_event_from_record(r) for r in monitoring_repository.get_unacknowledged_events(conn)]


def _event_to_record(event: MonitoringEvent) -> MonitoringEventRecord:
    return MonitoringEventRecord(
        event_id=event.event_id, monitoring_run_id=event.monitoring_run_id, saved_search_id=event.saved_search_id,
        saved_search_version=event.saved_search_version, event_type=event.event_type, severity=event.severity,
        significance=event.significance, explanation=event.explanation, evidence=event.evidence,
        detected_at=event.detected_at, dedup_key=event.dedup_key, metadata=event.metadata,
        search_id=event.search_id, apartment_id=event.apartment_id, platform_id=event.platform_id,
        connector_id=event.connector_id, old_value=event.old_value, new_value=event.new_value,
        acknowledged=event.acknowledged, notification_eligible=event.notification_eligible, id=event.id,
    )


def _event_from_record(record: MonitoringEventRecord) -> MonitoringEvent:
    return MonitoringEvent(
        saved_search_id=record.saved_search_id, saved_search_version=record.saved_search_version,
        monitoring_run_id=record.monitoring_run_id, event_type=record.event_type, severity=record.severity,
        significance=record.significance, explanation=record.explanation, evidence=record.evidence,
        detected_at=record.detected_at, dedup_key=record.dedup_key, search_id=record.search_id,
        apartment_id=record.apartment_id, platform_id=record.platform_id, connector_id=record.connector_id,
        old_value=record.old_value, new_value=record.new_value, acknowledged=record.acknowledged,
        notification_eligible=record.notification_eligible, metadata=record.metadata, event_id=record.event_id,
        id=record.id,
    )


# --------------------------------------------------------------------------- #
# statistics + report artifacts
# --------------------------------------------------------------------------- #


def record_statistics(conn: sqlite3.Connection, statistics: MonitoringStatistics) -> int:
    return monitoring_repository.add_statistics(
        conn, MonitoringStatisticsRecord(monitoring_run_id=statistics.monitoring_run_id, computed_at=statistics.computed_at, statistics=statistics.as_dict()),
    )


def get_statistics_for_run(conn: sqlite3.Connection, monitoring_run_id: str) -> dict | None:
    record = monitoring_repository.get_statistics_for_run(conn, monitoring_run_id)
    return record.statistics if record is not None else None


def record_report_artifact(conn: sqlite3.Connection, monitoring_run_id: str, report_type: str, path: str, generated_at: datetime) -> int:
    return monitoring_repository.add_report_artifact(
        conn, ReportArtifactRecord(monitoring_run_id=monitoring_run_id, report_type=report_type, path=path, generated_at=generated_at),
    )


def get_report_artifacts_for_run(conn: sqlite3.Connection, monitoring_run_id: str) -> list[ReportArtifactRecord]:
    return monitoring_repository.get_report_artifacts_for_run(conn, monitoring_run_id)
