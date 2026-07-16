"""`compute_statistics()` — computed *from* one batch's already-persisted
deliveries/attempts, never inside `NotificationEngine` itself. Mirrors
`monitoring/statistics.py`'s own "single responsibility" separation.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.notifications import service
from src.notifications.models import NotificationStatistics


def compute_statistics(conn: sqlite3.Connection, batch_id: str, *, now: datetime) -> NotificationStatistics:
    deliveries = service.get_deliveries_for_batch(conn, batch_id)

    by_status: dict[str, int] = {}
    suppressed = 0
    quiet_hours_deferred = 0
    rate_limited = 0
    channel_success: dict[str, int] = {}
    channel_failure: dict[str, int] = {}

    for delivery in deliveries:
        by_status[delivery.status.value] = by_status.get(delivery.status.value, 0) + 1
        if delivery.status.value == "suppressed":
            suppressed += 1
            if delivery.notes and "quiet hours" in delivery.notes:
                quiet_hours_deferred += 1
            if delivery.notes and "rate limit" in delivery.notes:
                rate_limited += 1
        for attempt in service.get_attempts_for_delivery(conn, delivery.delivery_id):
            if attempt.status == "delivered":
                channel_success[attempt.channel] = channel_success.get(attempt.channel, 0) + 1
            else:
                channel_failure[attempt.channel] = channel_failure.get(attempt.channel, 0) + 1

    return NotificationStatistics(
        batch_id=batch_id, computed_at=now, deliveries_by_status=by_status, suppressed_count=suppressed,
        rate_limited_count=rate_limited, quiet_hours_deferred_count=quiet_hours_deferred,
        channel_success_counts=channel_success, channel_failure_counts=channel_failure,
    )
