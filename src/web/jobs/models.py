"""`Job` — the domain-layer shape for a background unit of work, distinct from
`storage.models.WebJobRecord` (the persisted row) the same way
`NotificationDelivery`/`NotificationDeliveryRecord` are kept distinct
elsewhere in this codebase — translated by `service.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.web.constants import JOB_STATUS_PENDING


class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    job_type: str
    status: str = JOB_STATUS_PENDING
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    profile_id: str | None = None
    request_reference: str | None = None
    progress: float = 0.0
    current_stage: str | None = None
    result_reference: str | None = None
    error_summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    cancellation_requested: bool = False
    metadata: dict = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        from src.web.constants import TERMINAL_JOB_STATUSES

        return self.status in TERMINAL_JOB_STATUSES
