"""Unit tests for AvailabilityImportanceRule/PropertyTypePreferenceRule/
MinimumAreaRule/NumberOfRoomsRule/PlatformPreferenceRule —
src/feedback/rules/listing_rules.py.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.feedback.base_rule import PreferenceContext
from src.feedback.event_types import FeedbackEventType
from src.feedback.models import FeedbackEvent
from src.feedback.rules.listing_rules import (
    AvailabilityImportanceRule,
    MinimumAreaRule,
    NumberOfRoomsRule,
    PlatformPreferenceRule,
    PropertyTypePreferenceRule,
)
from src.storage.models import Apartment

_NOW = datetime.now(timezone.utc)


def _apartment(**kwargs) -> Apartment:
    defaults = dict(
        id="apt-1", platform_id="p1", platform_listing_id="l1", title="T", url="u", current_price=1000,
        current_status="available", first_seen_at=_NOW, last_seen_at=_NOW,
    )
    defaults.update(kwargs)
    return Apartment(**defaults)


class AvailabilityImportanceRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = AvailabilityImportanceRule()

    def test_saved_available_listing_is_supporting(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = self.rule.observe(event, PreferenceContext(apartment=_apartment(current_status="available")))
        self.assertEqual(observation.direction, "supporting")

    def test_saved_unavailable_listing_is_opposing(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = self.rule.observe(event, PreferenceContext(apartment=_apartment(current_status="delisted")))
        self.assertEqual(observation.direction, "opposing")

    def test_rejected_available_listing_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.REJECTED, occurred_at=_NOW, source="cli")
        observation = self.rule.observe(event, PreferenceContext(apartment=_apartment(current_status="available")))
        self.assertIsNone(observation)

    def test_rejected_unavailable_listing_is_supporting(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.REJECTED, occurred_at=_NOW, source="cli")
        observation = self.rule.observe(event, PreferenceContext(apartment=_apartment(current_status="delisted")))
        self.assertEqual(observation.direction, "supporting")


class PropertyTypePreferenceRuleTests(unittest.TestCase):
    def test_missing_property_type_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = PropertyTypePreferenceRule().observe(event, PreferenceContext(apartment=_apartment(property_type=None)))
        self.assertIsNone(observation)

    def test_present_property_type_produces_categorical_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = PropertyTypePreferenceRule().observe(event, PreferenceContext(apartment=_apartment(property_type="studio")))
        self.assertEqual(observation.observed_value, {"category": "studio"})


class MinimumAreaRuleTests(unittest.TestCase):
    def test_missing_sqft_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        self.assertIsNone(MinimumAreaRule().observe(event, PreferenceContext(apartment=_apartment(sqft=None))))

    def test_present_sqft_produces_threshold_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = MinimumAreaRule().observe(event, PreferenceContext(apartment=_apartment(sqft=650)))
        self.assertEqual(observation.observed_value, {"value": 650})


class NumberOfRoomsRuleTests(unittest.TestCase):
    def test_missing_bedrooms_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        self.assertIsNone(NumberOfRoomsRule().observe(event, PreferenceContext(apartment=_apartment(bedrooms=None))))

    def test_present_bedrooms_produces_threshold_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = NumberOfRoomsRule().observe(event, PreferenceContext(apartment=_apartment(bedrooms=2)))
        self.assertEqual(observation.observed_value, {"value": 2})


class PlatformPreferenceRuleTests(unittest.TestCase):
    def test_produces_categorical_evidence_from_platform_id(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = PlatformPreferenceRule().observe(event, PreferenceContext(apartment=_apartment(platform_id="rentcast")))
        self.assertEqual(observation.observed_value, {"category": "rentcast"})


if __name__ == "__main__":
    unittest.main()
