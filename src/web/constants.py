"""Constants shared across the web package — see docs/32_Web_Dashboard.md
"Single-User Today, Multi-User Tomorrow".
"""

from __future__ import annotations

# v1 is single-local-user by design (the mission's own words): every facade
# method that needs a `profile_id` gets this fixed constant rather than a
# per-request login. The only future change to support multiple users is
# *where this value comes from* (a session/auth lookup instead of a
# constant) — every call site already threads `profile_id` through, exactly
# like `feedback`/`notifications`/`monitoring` already do internally.
DEFAULT_PROFILE_ID = "local-user"

API_PREFIX = "/api/v1"

JOB_TYPE_SEARCH = "search"
JOB_TYPE_MONITORING_RUN = "monitoring_run"
JOB_TYPE_DISCOVERY_RUN = "discovery_run"

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_PARTIAL = "partial"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"

ALL_JOB_STATUSES = frozenset({
    JOB_STATUS_PENDING, JOB_STATUS_RUNNING, JOB_STATUS_COMPLETED,
    JOB_STATUS_PARTIAL, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED,
})

TERMINAL_JOB_STATUSES = frozenset({
    JOB_STATUS_COMPLETED, JOB_STATUS_PARTIAL, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED,
})
