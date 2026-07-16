"""Shared shapes for the Notification Delivery Engine. See
docs/31_Notification_Delivery.md "Architecture".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class NotificationChannelName:
    """Open-ended by design, same convention `MonitoringEventType`/
    `FeedbackEventType` already established — a future channel is a new string
    constant plus one registered `NotificationChannel`, never a code change here.
    """

    CONSOLE = "console"
    FILE = "file"
    EMAIL = "email"
    WEBHOOK = "webhook"


class NotificationDeliveryStatus(str, Enum):
    PENDING = "pending"
    ELIGIBLE = "eligible"
    SUPPRESSED = "suppressed"
    QUEUED = "queued"
    SENDING = "sending"
    DELIVERED = "delivered"
    PARTIALLY_DELIVERED = "partially_delivered"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    CANCELLED = "cancelled"
    ACKNOWLEDGED = "acknowledged"


@dataclass
class NotificationPolicy:
    """Engine-level retry/backoff/dead-letter configuration — distinct from
    `NotificationPreferenceVersion` (per-user channel/content/quiet-hours
    preferences), the same "deployment knob vs. per-item policy" separation
    `MonitoringConfiguration.default_policy`/`MonitoringPolicy` already made in
    Step 14.
    """

    retry_max_attempts: int = 3
    retry_backoff_base_seconds: float = 30.0
    retry_backoff_max_seconds: float = 3600.0
    retryable_error_categories: list[str] = field(default_factory=lambda: ["timeout", "connection_error", "server_error"])
    non_retryable_error_categories: list[str] = field(default_factory=lambda: ["invalid_configuration", "rejected", "unauthorized"])
    dead_letter_after_attempts: int = 5


@dataclass
class NotificationConfiguration:
    default_policy: NotificationPolicy = field(default_factory=NotificationPolicy)
    default_worker_id: str = "manual-cli"


@dataclass
class NotificationPreference:
    preference_id: str
    profile_id: str
    current_version: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
    saved_search_id: str | None = None
    id: int | None = None


@dataclass
class NotificationPreferenceVersion:
    """One immutable preference definition — "Never overwrite preferences.
    Every change creates a new immutable NotificationPreferenceVersion" (the
    mission's own words). Every field the mission's own NOTIFICATION
    PREFERENCES section names.
    """

    preference_id: str
    version: int
    enabled_channels: list[str]
    event_types: list[str]  # empty = every type eligible
    immediate_event_types: list[str]
    digest_event_types: list[str]
    timezone: str
    include_images: bool
    include_original_urls: bool
    include_ranking_explanation: bool
    include_geo_summary: bool
    include_preference_explanation: bool
    include_report_links: bool
    language: str
    format: str  # "text" | "html"
    metadata: dict
    created_at: datetime
    minimum_severity: str | None = None
    minimum_significance: float = 0.0
    digest_frequency: str | None = None  # "hourly" | "daily" | "weekly" | "manual" | None (no digest)
    quiet_hours_start: str | None = None  # "HH:MM"
    quiet_hours_end: str | None = None
    max_per_hour: int | None = None
    max_per_day: int | None = None
    id: int | None = None


@dataclass
class NotificationChannelResult:
    """Every channel `send()`/`send_batch()` call returns this — "Every send
    operation must return a structured delivery result" (the mission's own
    words).
    """

    channel: str
    success: bool
    error: str | None = None
    error_category: str | None = None
    duration_ms: int | None = None
    external_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class NotificationMessage:
    """One rendered message for one delivery on one channel — reproducible:
    the same `template_name`/`template_version` plus the same stored context
    always renders the same output.
    """

    delivery_id: str
    profile_id: str
    event_ids: list[str]
    channel: str
    body_text: str
    template_name: str
    template_version: int
    language: str
    generated_at: datetime
    saved_search_id: str | None = None
    saved_search_version: int | None = None
    monitoring_run_id: str | None = None
    subject: str | None = None
    body_html: str | None = None
    original_listing_urls: list[str] = field(default_factory=list)
    report_links: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class NotificationAttempt:
    delivery_id: str
    channel: str
    attempt_number: int
    status: str  # "delivered" | "failed"
    attempted_at: datetime
    error: str | None = None
    error_category: str | None = None
    duration_ms: int | None = None
    id: int | None = None


@dataclass
class NotificationDigest:
    delivery_id: str
    frequency: str
    period_start: datetime
    period_end: datetime
    event_ids: list[str]
    generated_at: datetime


@dataclass
class NotificationBatch:
    batch_type: str  # "immediate" | "digest" | "retry"
    started_at: datetime
    completed_at: datetime | None = None
    deliveries_attempted: int = 0
    deliveries_succeeded: int = 0
    deliveries_failed: int = 0
    notes: str | None = None
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    id: int | None = None


@dataclass
class NotificationDelivery:
    profile_id: str
    preference_id: str
    preference_version: int
    is_digest: bool
    status: NotificationDeliveryStatus
    channels: list[str]
    event_ids: list[str]
    dedup_key: str
    idempotency_key: str
    created_at: datetime
    batch_id: str | None = None
    saved_search_id: str | None = None
    saved_search_version: int | None = None
    next_attempt_at: datetime | None = None
    attempt_count: int = 0
    acknowledged: bool = False
    notes: str | None = None
    delivery_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    id: int | None = None


@dataclass
class NotificationEligibility:
    """The result of `evaluate_event()` — deterministic and explainable (the
    mission's own words): every reason an event was or wasn't included is
    named, never a bare boolean.
    """

    event_id: str
    eligible: bool
    eligible_channels: list[str] = field(default_factory=list)
    ineligible_reasons: dict[str, str] = field(default_factory=dict)  # channel -> reason, or "*" -> reason
    is_immediate: bool = False
    is_digest_only: bool = False
    deferred_to: datetime | None = None


@dataclass
class NotificationStatistics:
    batch_id: str
    computed_at: datetime
    deliveries_by_status: dict[str, int] = field(default_factory=dict)
    suppressed_count: int = 0
    rate_limited_count: int = 0
    quiet_hours_deferred_count: int = 0
    channel_success_counts: dict[str, int] = field(default_factory=dict)
    channel_failure_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "batch_id": self.batch_id, "computed_at": self.computed_at.isoformat(),
            "deliveries_by_status": self.deliveries_by_status, "suppressed_count": self.suppressed_count,
            "rate_limited_count": self.rate_limited_count, "quiet_hours_deferred_count": self.quiet_hours_deferred_count,
            "channel_success_counts": self.channel_success_counts, "channel_failure_counts": self.channel_failure_counts,
        }


@dataclass
class NotificationHealth:
    channel: str
    recent_success_count: int
    recent_failure_count: int
    last_success_at: datetime | None
    last_failure_at: datetime | None

    @property
    def is_healthy(self) -> bool:
        return self.recent_failure_count == 0 or self.recent_success_count > self.recent_failure_count
