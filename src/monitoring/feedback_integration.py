"""Turns an explicit user reaction to a `MonitoringEvent` into feedback
evidence — never called automatically by `MonitoringEngine.run_now()`/
`run_due()` itself. See docs/30_Continuous_Monitoring.md "Feedback Engine
Integration" — "Do not infer user preference merely because an event was
generated" (the mission's own words): a `MonitoringEvent` existing is not
evidence of anything about the user; only a real, named reaction to it is.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.feedback import FeedbackEngine, FeedbackEvent
from src.feedback.event_types import FeedbackEventType
from src.monitoring import service
from src.monitoring.exceptions import MonitoringValidationError

# Only reactions the mission explicitly names as appropriate feedback evidence
# ("user saves a newly discovered match," "user ignores repeated events,"
# "user opens the original listing," "user rejects a recommendation").
_REACTION_TO_EVENT_TYPE = {
    "saved": FeedbackEventType.SAVED,
    "ignored": FeedbackEventType.IGNORED,
    "opened_original": FeedbackEventType.ORIGINAL_LISTING_OPENED,
    "rejected": FeedbackEventType.REJECTED,
}


def record_user_reaction(
    conn: sqlite3.Connection, feedback_engine: FeedbackEngine, profile_id: str, event_id: str, reaction: str, occurred_at: datetime,
) -> FeedbackEvent:
    if reaction not in _REACTION_TO_EVENT_TYPE:
        raise MonitoringValidationError(f"Unknown reaction {reaction!r} — expected one of {sorted(_REACTION_TO_EVENT_TYPE)}")

    event = service.get_event(conn, event_id)
    if event is None:
        raise MonitoringValidationError(f"No such monitoring event {event_id!r}")

    feedback_event = FeedbackEvent(
        profile_id=profile_id, event_type=_REACTION_TO_EVENT_TYPE[reaction], occurred_at=occurred_at, source="monitoring",
        apartment_id=event.apartment_id, metadata={"monitoring_event_id": event_id, "monitoring_event_type": event.event_type},
    )
    return feedback_engine.record_event(conn, feedback_event)
