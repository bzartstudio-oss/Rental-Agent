"""Unit tests for PriceSensitivityRule/MaximumBudgetRule — src/feedback/rules/price_rules.py."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.feedback.base_rule import PreferenceContext
from src.feedback.event_types import FeedbackEventType
from src.feedback.models import FeedbackEvent
from src.feedback.rules.price_rules import MaximumBudgetRule, PriceSensitivityRule
from src.storage.database import Database
from src.storage.models import Apartment, Platform

_NOW = datetime.now(timezone.utc)


def _apartment(price: float) -> Apartment:
    return Apartment(
        id="apt-1", platform_id="p1", platform_listing_id="l1", title="T", url="u", current_price=price,
        current_status="available", first_seen_at=_NOW, last_seen_at=_NOW,
    )


class PriceSensitivityRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = PriceSensitivityRule()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_no_context_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = self.rule.observe(event, PreferenceContext(apartment=_apartment(1000)))
        self.assertIsNone(observation)

    def test_no_city_average_yet_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        with self.db.transaction() as conn:
            observation = self.rule.observe(event, PreferenceContext(conn=conn, apartment=_apartment(1000), location="X"))
        self.assertIsNone(observation)


class MaximumBudgetRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = MaximumBudgetRule()

    def test_no_apartment_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        self.assertIsNone(self.rule.observe(event, PreferenceContext()))

    def test_saved_apartment_produces_a_supporting_observation(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = self.rule.observe(event, PreferenceContext(apartment=_apartment(1500)))
        self.assertEqual(observation.direction, "supporting")
        self.assertEqual(observation.observed_value, {"value": 1500})

    def test_irrelevant_event_type_is_ignored(self) -> None:
        self.assertNotIn(FeedbackEventType.VIEWED, self.rule.relevant_event_types())


if __name__ == "__main__":
    unittest.main()
