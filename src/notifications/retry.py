"""Configurable retry behavior. See docs/31_Notification_Delivery.md "Retry
Policy" — "Retries must be idempotent. A repeated attempt must not generate a
second logical notification" (the mission's own words): retrying always
reuses the same `NotificationDelivery` row (keyed by its own stable
`idempotency_key`), never creates a new one.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.notifications.models import NotificationPolicy


def is_retryable(error_category: str | None, policy: NotificationPolicy) -> bool:
    if error_category in policy.non_retryable_error_categories:
        return False
    return True  # unknown/unlisted categories default to retryable, same as `error_category is None`


def should_dead_letter(attempt_count: int, policy: NotificationPolicy) -> bool:
    return attempt_count >= policy.dead_letter_after_attempts


def compute_next_attempt_at(attempt_count: int, policy: NotificationPolicy, now: datetime) -> datetime:
    """Exponential backoff, capped at `retry_backoff_max_seconds`."""
    delay = min(policy.retry_backoff_base_seconds * (2 ** max(0, attempt_count - 1)), policy.retry_backoff_max_seconds)
    return now + timedelta(seconds=delay)
