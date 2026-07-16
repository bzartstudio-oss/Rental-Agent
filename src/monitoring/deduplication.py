"""Event deduplication. See docs/30_Continuous_Monitoring.md "Event
Deduplication" — "Prevent repeated runs from creating duplicate events for the
same unchanged condition ... Do not delete duplicate evidence" (the mission's
own words): a suppressed duplicate is simply never written (nothing to
delete), and the suppression itself is counted in `MonitoringStatistics`, not
silently dropped.
"""

from __future__ import annotations

from datetime import datetime

from src.monitoring import service
from src.monitoring.models import MonitoringPolicy


def make_dedup_key(saved_search_id: str, subject_id: str, event_type: str) -> str:
    """`subject_id` is whatever this event is about — an apartment id, a
    platform id, or a fixed literal for a run-level event — "Deduplicate
    using: saved search, apartment or platform, event type, normalized old/new
    values" (the mission's own words); old/new values are checked separately
    in `is_duplicate()` rather than folded into the key itself, so the same
    key's history can distinguish "still the same change" from "a new change
    to the same subject."
    """
    return f"{saved_search_id}:{subject_id}:{event_type}"


def is_duplicate(conn, dedup_key: str, new_value: dict | None, policy: MonitoringPolicy, now: datetime) -> bool:
    """True when the most recent event under this `dedup_key` reported the
    same `new_value` within `policy.event_dedup_window_minutes` — the same
    condition repeated, not a genuinely new change.
    """
    previous_events = service.get_events_by_dedup_key(conn, dedup_key)
    if not previous_events:
        return False

    most_recent = previous_events[0]  # get_events_by_dedup_key orders newest-first
    age_minutes = (now - most_recent.detected_at).total_seconds() / 60
    if age_minutes > policy.event_dedup_window_minutes:
        return False

    return most_recent.new_value == new_value
