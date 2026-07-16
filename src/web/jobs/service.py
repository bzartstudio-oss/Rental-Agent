"""Thin storage orchestration for `Job` — mirrors `monitoring/service.py`'s
own "translate domain <-> record, nothing else" shape.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.storage import web_repository
from src.storage.models import WebJobRecord
from src.web.jobs.models import Job


def _to_record(job: Job) -> WebJobRecord:
    return WebJobRecord(
        job_id=job.job_id, job_type=job.job_type, profile_id=job.profile_id,
        request_reference=job.request_reference, status=job.status, progress=job.progress,
        current_stage=job.current_stage, result_reference=job.result_reference,
        error_summary=job.error_summary, warnings=job.warnings,
        cancellation_requested=job.cancellation_requested, metadata=job.metadata,
        created_at=job.created_at, started_at=job.started_at, completed_at=job.completed_at,
    )


def _from_record(record: WebJobRecord) -> Job:
    return Job(
        job_id=record.job_id, job_type=record.job_type, profile_id=record.profile_id,
        request_reference=record.request_reference, status=record.status, progress=record.progress,
        current_stage=record.current_stage, result_reference=record.result_reference,
        error_summary=record.error_summary, warnings=record.warnings,
        cancellation_requested=record.cancellation_requested, metadata=record.metadata,
        created_at=record.created_at, started_at=record.started_at, completed_at=record.completed_at,
    )


def record_job(conn: sqlite3.Connection, job: Job) -> None:
    web_repository.add_job(conn, _to_record(job))


def update_job(conn: sqlite3.Connection, job: Job) -> None:
    web_repository.update_job(conn, _to_record(job))


def get_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    record = web_repository.get_job(conn, job_id)
    return _from_record(record) if record is not None else None


def list_recent_jobs(conn: sqlite3.Connection, *, profile_id: str | None = None, limit: int = 20) -> list[Job]:
    return [_from_record(r) for r in web_repository.get_recent_jobs(conn, profile_id=profile_id, limit=limit)]


def list_active_jobs(conn: sqlite3.Connection) -> list[Job]:
    return [_from_record(r) for r in web_repository.get_active_jobs(conn)]


def request_cancellation(conn: sqlite3.Connection, job_id: str) -> Job | None:
    """Sets the cancellation flag only — the running background thread is
    responsible for honoring it at its next safe checkpoint (see
    `runner.py`). A job already in a terminal state is left untouched.
    """
    job = get_job(conn, job_id)
    if job is None or job.is_terminal:
        return job
    job.cancellation_requested = True
    update_job(conn, job)
    return job
