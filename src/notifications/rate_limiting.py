"""Per-profile/per-channel rate limiting. See
docs/31_Notification_Delivery.md "Rate Limiting" — "Rate-limit suppression
must be stored and explainable. Do not silently discard eligible events" (the
mission's own words): a rate-limited send is never dropped — the caller
records it as `SUPPRESSED` and the underlying `MonitoringEvent` remains
available for a later digest.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from src.notifications import service
from src.notifications.models import NotificationPreferenceVersion


def is_rate_limited(conn: sqlite3.Connection, profile_id: str, channel: str, preference_version: NotificationPreferenceVersion, now: datetime) -> bool:
    if preference_version.max_per_hour is not None:
        count = service.count_rate_limit_observations_since(conn, profile_id, channel, now - timedelta(hours=1))
        if count >= preference_version.max_per_hour:
            return True
    if preference_version.max_per_day is not None:
        count = service.count_rate_limit_observations_since(conn, profile_id, channel, now - timedelta(days=1))
        if count >= preference_version.max_per_day:
            return True
    return False


def record_send(conn: sqlite3.Connection, profile_id: str, channel: str, now: datetime) -> None:
    service.record_rate_limit_observation(conn, profile_id, channel, now)
