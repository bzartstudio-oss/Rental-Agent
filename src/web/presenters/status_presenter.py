"""Small, shared display-only helpers (a severity -> CSS class, a job status
-> badge label) reused across dashboard/monitoring/notifications/health
templates — never a business decision, only a label for an already-decided
value.
"""

from __future__ import annotations

_SEVERITY_CLASS = {"info": "badge-info", "warning": "badge-warning", "critical": "badge-critical"}
_JOB_STATUS_CLASS = {
    "pending": "badge-pending", "running": "badge-running", "completed": "badge-success",
    "partial": "badge-warning", "failed": "badge-critical", "cancelled": "badge-pending",
}
_DELIVERY_STATUS_CLASS = {
    "pending": "badge-pending", "delivered": "badge-success", "partially_delivered": "badge-warning",
    "retry_scheduled": "badge-pending", "failed": "badge-critical", "suppressed": "badge-pending",
    "cancelled": "badge-pending",
}


def severity_css_class(severity: str) -> str:
    return _SEVERITY_CLASS.get(severity, "badge-pending")


def job_status_css_class(status: str) -> str:
    return _JOB_STATUS_CLASS.get(status, "badge-pending")


def delivery_status_css_class(status: str) -> str:
    return _DELIVERY_STATUS_CLASS.get(status, "badge-pending")


def health_badge(is_healthy: bool) -> str:
    return "badge-success" if is_healthy else "badge-critical"
