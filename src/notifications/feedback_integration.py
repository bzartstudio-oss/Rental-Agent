"""Turns an explicit user reaction to a delivered notification into feedback
evidence — never called automatically by `NotificationEngine
.process_pending_deliveries()`/`process_due_digests()` themselves. See
docs/31_Notification_Delivery.md "Feedback Integration" — "Do not infer
preference merely because a notification was delivered" (the mission's own
words): a `NotificationDelivery` existing is not evidence of anything about
the user; only a real, named reaction to it is. Mirrors
`monitoring/feedback_integration.py`'s own shape exactly.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.feedback import FeedbackEngine, FeedbackEvent
from src.feedback.event_types import FeedbackEventType
from src.notifications import service
from src.notifications.exceptions import NotificationValidationError

# Only reactions the mission explicitly names as appropriate feedback evidence
# ("notification opened," "original listing opened," "alert dismissed,"
# "apartment saved," "apartment rejected").
_REACTION_TO_EVENT_TYPE = {
    "notification_opened": FeedbackEventType.NOTIFICATION_OPENED,
    "original_listing_opened": FeedbackEventType.ORIGINAL_LISTING_OPENED,
    "dismissed": FeedbackEventType.NOTIFICATION_DISMISSED,
    "saved": FeedbackEventType.SAVED,
    "rejected": FeedbackEventType.REJECTED,
}


def record_user_reaction(
    conn: sqlite3.Connection, feedback_engine: FeedbackEngine, profile_id: str, delivery_id: str, reaction: str, occurred_at: datetime,
) -> FeedbackEvent:
    if reaction not in _REACTION_TO_EVENT_TYPE:
        raise NotificationValidationError(f"Unknown reaction {reaction!r} — expected one of {sorted(_REACTION_TO_EVENT_TYPE)}")

    delivery = service.get_delivery(conn, delivery_id)
    if delivery is None:
        raise NotificationValidationError(f"No such notification delivery {delivery_id!r}")

    apartment_id = None
    if len(delivery.event_ids) == 1:
        from src.monitoring import service as monitoring_service

        event = monitoring_service.get_event(conn, delivery.event_ids[0])
        apartment_id = event.apartment_id if event else None

    feedback_event = FeedbackEvent(
        profile_id=profile_id, event_type=_REACTION_TO_EVENT_TYPE[reaction], occurred_at=occurred_at, source="notification",
        apartment_id=apartment_id, metadata={"delivery_id": delivery_id, "event_ids": delivery.event_ids},
    )
    return feedback_engine.record_event(conn, feedback_event)
