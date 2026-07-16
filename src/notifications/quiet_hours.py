"""Timezone-aware quiet hours. See docs/31_Notification_Delivery.md "Quiet
Hours" — "Use timezone-aware datetimes" (the mission's own words): every
comparison here happens in the preference's own configured timezone, never
the server's local time or a naive UTC comparison.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.notifications.models import NotificationPreferenceVersion


def is_in_quiet_hours(preference_version: NotificationPreferenceVersion, now: datetime) -> bool:
    if not preference_version.quiet_hours_start or not preference_version.quiet_hours_end:
        return False

    local_now = _to_local(now, preference_version.timezone)
    start = _parse_hhmm(preference_version.quiet_hours_start)
    end = _parse_hhmm(preference_version.quiet_hours_end)
    current = local_now.time()

    if start <= end:
        return start <= current < end
    return current >= start or current < end  # wraps past midnight, e.g. 22:00-07:00


def next_permitted_time(preference_version: NotificationPreferenceVersion, now: datetime) -> datetime:
    """The next moment quiet hours end, in the same timezone `now` was given
    in — "Deferred events should be eligible for the next permitted delivery
    window" (the mission's own words).
    """
    if not is_in_quiet_hours(preference_version, now):
        return now

    tz = ZoneInfo(preference_version.timezone)
    local_now = _to_local(now, preference_version.timezone)
    end = _parse_hhmm(preference_version.quiet_hours_end)
    candidate = local_now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(now.tzinfo or tz)


def _to_local(now: datetime, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    aware = now if now.tzinfo is not None else now.replace(tzinfo=tz)
    return aware.astimezone(tz)


def _parse_hhmm(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":"))
    return time(hour=hour, minute=minute)
