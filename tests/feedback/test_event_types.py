"""Unit tests for FeedbackEventType — src/feedback/event_types.py."""

from __future__ import annotations

import unittest

from src.feedback.event_types import (
    EXPLICIT_EVENT_TYPES,
    KNOWN_EVENT_TYPES,
    NEGATIVE_EVENT_TYPES,
    POSITIVE_EVENT_TYPES,
    FeedbackEventType,
)


class FeedbackEventTypeTests(unittest.TestCase):
    def test_all_16_mission_event_types_are_present(self) -> None:
        expected = {
            "viewed", "saved", "shortlisted", "rejected", "contacted", "ignored",
            "manual_rating", "manual_ranking_up", "manual_ranking_down",
            "filter_selected", "filter_removed", "weight_changed", "search_repeated",
            "result_opened", "original_listing_opened",
            # v2.5 Step 15 (Notification Delivery Engine) additions — explicit
            # user reactions to a delivered notification, never inferred from
            # delivery alone.
            "notification_opened", "notification_dismissed",
        }
        self.assertEqual(KNOWN_EVENT_TYPES, frozenset(expected))

    def test_a_future_event_type_is_just_a_string_no_registry_needed(self) -> None:
        """"Future event types must be addable without changing FeedbackEngine"
        (the mission's own words) — nothing anywhere validates `event_type`
        against `KNOWN_EVENT_TYPES`, so a brand-new string works immediately.
        """
        from src.feedback.models import FeedbackEvent
        from datetime import datetime, timezone

        event = FeedbackEvent(profile_id="u1", event_type="a_future_event_type", occurred_at=datetime.now(timezone.utc), source="cli")
        self.assertEqual(event.event_type, "a_future_event_type")

    def test_explicit_types_are_a_subset_of_known(self) -> None:
        self.assertTrue(EXPLICIT_EVENT_TYPES.issubset(KNOWN_EVENT_TYPES))

    def test_positive_and_negative_types_do_not_overlap(self) -> None:
        self.assertEqual(POSITIVE_EVENT_TYPES & NEGATIVE_EVENT_TYPES, frozenset())

    def test_feedback_event_type_constants_match_known_set(self) -> None:
        self.assertIn(FeedbackEventType.SAVED, KNOWN_EVENT_TYPES)
        self.assertIn(FeedbackEventType.MANUAL_RATING, KNOWN_EVENT_TYPES)


if __name__ == "__main__":
    unittest.main()
