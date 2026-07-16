"""Records repeated filter choices as feedback evidence — "Record repeated filter
choices as feedback evidence. Do not silently convert preferred filters into
required filters. Required conditions must remain explicit user decisions" (the
mission's own words). See docs/28_User_Feedback_and_Preference_Learning.md
"Filter Engine Integration".

This module only *observes* — it never reads back into `SearchRequest.criteria`
or `FilterEngine`'s own hard-filter behavior. A filter choice recorded here can
only ever surface later as a *suggested* preference (via `ranking_adapter`) or a
learned `PreferenceValue`, never as a silently-added hard constraint.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.feedback.engine import FeedbackEngine
from src.feedback.event_types import FeedbackEventType
from src.feedback.models import FeedbackEvent


def record_filter_selection_events(
    engine: FeedbackEngine, conn: sqlite3.Connection, profile_id: str, criteria: dict,
    *, occurred_at: datetime, search_id: str | None = None, source: str = "search_request",
) -> list[FeedbackEvent]:
    """One `FILTER_SELECTED` event per criterion in `criteria` — the exact,
    already-active filter set for this search, recorded as-is.
    """
    recorded = []
    for key, value in criteria.items():
        event = FeedbackEvent(
            profile_id=profile_id, event_type=FeedbackEventType.FILTER_SELECTED, occurred_at=occurred_at,
            source=source, search_id=search_id, event_value={"key": key, "value": value},
        )
        recorded.append(engine.record_event(conn, event))
    return recorded


def record_filter_change_events(
    engine: FeedbackEngine, conn: sqlite3.Connection, profile_id: str,
    previous_criteria: dict, new_criteria: dict,
    *, occurred_at: datetime, search_id: str | None = None, source: str = "search_request",
) -> list[FeedbackEvent]:
    """Diffs two criteria sets (e.g. this search vs. the previous one for the same
    profile) — a changed or newly-added key is `FILTER_SELECTED`; a key present
    before but absent now is `FILTER_REMOVED`. Neither event type ever mutates
    `new_criteria` itself.
    """
    recorded = []
    for key, value in new_criteria.items():
        if previous_criteria.get(key) != value:
            event = FeedbackEvent(
                profile_id=profile_id, event_type=FeedbackEventType.FILTER_SELECTED, occurred_at=occurred_at,
                source=source, search_id=search_id, event_value={"key": key, "value": value},
            )
            recorded.append(engine.record_event(conn, event))

    for key, value in previous_criteria.items():
        if key not in new_criteria:
            event = FeedbackEvent(
                profile_id=profile_id, event_type=FeedbackEventType.FILTER_REMOVED, occurred_at=occurred_at,
                source=source, search_id=search_id, event_value={"key": key, "value": value},
            )
            recorded.append(engine.record_event(conn, event))

    return recorded
