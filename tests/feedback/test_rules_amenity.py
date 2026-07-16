"""Unit tests for the Group-B amenity preference rules —
src/feedback/rules/amenity_rules.py. All learn only from explicit filter
choices, never a listing outcome (no structured field exists for any of them).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.feedback.base_rule import PreferenceContext
from src.feedback.event_types import FeedbackEventType
from src.feedback.models import FeedbackEvent
from src.feedback.rules.amenity_rules import (
    NumberOfFlatmatesPreferenceRule,
    ParkingPreferenceRule,
    PrivateBathroomPreferenceRule,
    RoomTypePreferenceRule,
)

_NOW = datetime.now(timezone.utc)


class PrivateBathroomPreferenceRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = PrivateBathroomPreferenceRule()

    def test_filter_selected_true_supports_wanting_it(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.FILTER_SELECTED, occurred_at=_NOW,
                               source="cli", event_value={"key": "private_bathroom", "value": True})
        observation = self.rule.observe(event, PreferenceContext())
        self.assertEqual(observation.direction, "supporting")
        self.assertEqual(observation.source_type, "explicit")

    def test_filter_selected_false_opposes_wanting_it(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.FILTER_SELECTED, occurred_at=_NOW,
                               source="cli", event_value={"key": "private_bathroom", "value": False})
        observation = self.rule.observe(event, PreferenceContext())
        self.assertEqual(observation.direction, "opposing")

    def test_filter_removed_weakly_opposes(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.FILTER_REMOVED, occurred_at=_NOW,
                               source="cli", event_value={"key": "private_bathroom", "value": True})
        observation = self.rule.observe(event, PreferenceContext())
        self.assertEqual(observation.direction, "opposing")
        self.assertLess(observation.magnitude, 1.0)

    def test_a_different_filter_key_is_ignored(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.FILTER_SELECTED, occurred_at=_NOW,
                               source="cli", event_value={"key": "parking", "value": True})
        self.assertIsNone(self.rule.observe(event, PreferenceContext()))

    def test_metadata_declares_no_listing_field(self) -> None:
        self.assertFalse(self.rule.metadata().learns_from_listing_fields)


class ParkingPreferenceRuleTests(unittest.TestCase):
    def test_uses_its_own_preference_key(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.FILTER_SELECTED, occurred_at=_NOW,
                               source="cli", event_value={"key": "parking", "value": True})
        observation = ParkingPreferenceRule().observe(event, PreferenceContext())
        self.assertEqual(observation.preference_key, "parking")


class RoomTypePreferenceRuleTests(unittest.TestCase):
    def test_filter_selected_produces_categorical_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.FILTER_SELECTED, occurred_at=_NOW,
                               source="cli", event_value={"key": "room_type", "value": "private"})
        observation = RoomTypePreferenceRule().observe(event, PreferenceContext())
        self.assertEqual(observation.observed_value, {"category": "private"})

    def test_filter_removed_is_not_relevant(self) -> None:
        self.assertNotIn(FeedbackEventType.FILTER_REMOVED, RoomTypePreferenceRule().relevant_event_types())


class NumberOfFlatmatesPreferenceRuleTests(unittest.TestCase):
    def test_filter_selected_produces_threshold_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.FILTER_SELECTED, occurred_at=_NOW,
                               source="cli", event_value={"key": "number_of_flatmates", "value": 2})
        observation = NumberOfFlatmatesPreferenceRule().observe(event, PreferenceContext())
        self.assertEqual(observation.observed_value, {"value": 2.0})


if __name__ == "__main__":
    unittest.main()
