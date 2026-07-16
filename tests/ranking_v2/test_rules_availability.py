"""Unit tests for AvailabilityRankingRule — src/ranking_v2/rules/availability_rules.py."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.ranking_v2.base_rule import RankingContext
from src.ranking_v2.rules.availability_rules import AvailabilityRankingRule
from src.storage.models import Apartment


def _apartment(status: str) -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id="apt-1", platform_id="p1", platform_listing_id="l1", title="Test", url="u",
        current_price=1000, current_status=status, first_seen_at=now, last_seen_at=now,
    )


class AvailabilityRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = AvailabilityRankingRule()

    def test_available_scores_the_maximum_with_full_confidence(self) -> None:
        evidence = self.rule.evaluate(_apartment("available"), RankingContext())
        self.assertEqual(evidence.raw_score, 1.0)
        self.assertEqual(evidence.confidence, 1.0)
        self.assertEqual(evidence.detail, "Availability confirmed")

    def test_unavailable_scores_zero(self) -> None:
        evidence = self.rule.evaluate(_apartment("delisted"), RankingContext())
        self.assertEqual(evidence.raw_score, 0.0)
        self.assertIn("delisted", evidence.detail)

    def test_this_rule_never_lacks_evidence(self) -> None:
        """`current_status` is never `None` on a real `Apartment` — this is the one
        rule with unconditionally real evidence, no context required.
        """
        evidence = self.rule.evaluate(_apartment("available"), RankingContext())
        self.assertIsNotNone(evidence.raw_score)
        self.assertFalse(self.rule.metadata().requires_context)


if __name__ == "__main__":
    unittest.main()
