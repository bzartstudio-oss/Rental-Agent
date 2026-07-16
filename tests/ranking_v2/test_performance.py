"""Performance regression tests for the Intelligent Ranking Engine V2 — running all
12 real built-in rules against a real-sized apartment set, and confirming
registering many additional rules doesn't slow down lookup, must both stay fast.
Mirrors `tests/filter_engine/test_performance.py`/`tests/geography/test_*` same
"the whole point of a plugin architecture is that scale doesn't degrade the
framework" reasoning.
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from src.ranking_v2.base_rule import RankingContext, RankingRule
from src.ranking_v2.engine import RankingEngineV2
from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import RankingEvidence
from src.ranking_v2.profile import DEFAULT_PROFILE
from src.ranking_v2.registry import RankingRuleRegistry, register_ranking_rule
from src.storage.models import Apartment


class _BulkFakeRule(RankingRule):
    def evaluate(self, apartment, context: RankingContext) -> RankingEvidence:
        return RankingEvidence(rule_key=self.rule_key, raw_score=0.5, confidence=1.0, detail="x")

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(rule_key=self.rule_key, display_name=self.rule_key, category="test", description="")


def _apartments(count: int) -> list[Apartment]:
    now = datetime.now(timezone.utc)
    return [
        Apartment(
            id=f"a{i}", platform_id="p1", platform_listing_id=str(i), title=f"Place {i}", url="x",
            current_price=500 + i, current_status="available" if i % 3 else "delisted",
            first_seen_at=now, last_seen_at=now,
        )
        for i in range(count)
    ]


class RankingEngineV2PerformanceTests(unittest.TestCase):
    def test_ranking_500_apartments_with_all_built_in_rules_stays_fast(self) -> None:
        engine = RankingEngineV2(profile=DEFAULT_PROFILE)
        apartments = _apartments(500)

        started = time.perf_counter()
        ranked = engine.rank(apartments, RankingContext())
        elapsed_s = time.perf_counter() - started

        self.assertEqual(len(ranked), 500)
        self.assertLess(elapsed_s, 2.0, "ranking 500 apartments with 12 rules took too long")

    def test_registering_500_additional_rules_does_not_slow_down_lookup(self) -> None:
        registered_keys = []
        try:
            for i in range(500):
                key = f"bulk_fake_rule_{i}"
                rule = _BulkFakeRule()
                rule.rule_key = key
                register_ranking_rule(rule)
                registered_keys.append(key)

            started = time.perf_counter()
            for key in registered_keys:
                RankingRuleRegistry.get(key)
            elapsed_s = time.perf_counter() - started

            self.assertLess(elapsed_s, 1.0, "resolving 500 registered ranking rules took too long")
        finally:
            for key in registered_keys:
                RankingRuleRegistry._rules.pop(key, None)


if __name__ == "__main__":
    unittest.main()
