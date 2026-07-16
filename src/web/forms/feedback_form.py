"""Feedback action form — see docs/32_Web_Dashboard.md "Feedback Workflow".
See `src/feedback/event_types.py` for the full list of valid event types this
validates against — never invents a new event type here.
"""

from __future__ import annotations

from src.feedback.event_types import KNOWN_EVENT_TYPES
from src.web.error_handler import WebValidationError
from src.web.forms.validation import parse_optional_float, parse_safe_id, require_text


def parse_feedback_form(form) -> dict:
    event_type = require_text(form.get("event_type"), "Event type")
    if event_type not in KNOWN_EVENT_TYPES:
        raise WebValidationError(f"Unknown feedback event type {event_type!r}")

    apartment_id = form.get("apartment_id") or None
    if apartment_id:
        apartment_id = parse_safe_id(apartment_id, "Apartment id")

    rating = parse_optional_float(form.get("rating"), "Rating", minimum=0.0)
    event_value = {"rating": rating} if rating is not None else {}

    return {"event_type": event_type, "apartment_id": apartment_id, "event_value": event_value,
            "search_id": form.get("search_id") or None}
