"""Local job runner — see docs/32_Web_Dashboard.md "Job Model". A long-running
search/monitoring-run/discovery-run must not block the HTTP request that
started it; this package persists a `Job` record a browser can poll and
survive a page refresh (or server restart) with, and runs the actual work on a
background thread — no Redis/Celery required for one local user. See
`runner.py`'s own docstring for the future task-queue migration path.
"""

from __future__ import annotations

from src.web.jobs.models import Job, JobStatus
from src.web.jobs.runner import JobRunner
from src.web.jobs.service import get_job, list_active_jobs, list_recent_jobs, request_cancellation

__all__ = ["Job", "JobStatus", "JobRunner", "get_job", "list_active_jobs", "list_recent_jobs", "request_cancellation"]
