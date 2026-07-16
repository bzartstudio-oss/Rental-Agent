"""Unit + Explainability tests for RankingPipeline — src/ranking_v2/pipeline.py. Uses
a small, controlled set of fake rules (swapped into the real `RankingRuleRegistry`
for the duration of each test, then restored) so the renormalization/confidence/
explanation math can be verified exactly, independent of the 12 real built-in
rules' own behavior (covered separately in tests/ranking_v2/test_rules_*.py).
"""

from __future__ import annotations

import contextlib
import unittest
from datetime import datetime, timezone

from src.ranking_v2.base_rule import RankingContext, RankingRule
from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import RankingEvidence
from src.ranking_v2.pipeline import RankingPipeline
from src.ranking_v2.registry import RankingRuleRegistry
from src.ranking_v2.weights import RankingWeights
from src.storage.models import Apartment


class _FixedRule(RankingRule):
    def __init__(self, rule_key: str, raw_score, confidence, detail="a reason"):
        self.rule_key = rule_key
        self._raw_score = raw_score
        self._confidence = confidence
        self._detail = detail

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        return RankingEvidence(
            rule_key=self.rule_key, raw_score=self._raw_score, confidence=self._confidence, detail=self._detail,
        )

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(rule_key=self.rule_key, display_name=self.rule_key, category="test", description="")


@contextlib.contextmanager
def _isolated_rules(*rules: RankingRule):
    original = dict(RankingRuleRegistry._rules)
    RankingRuleRegistry._rules = {}
    try:
        for rule in rules:
            RankingRuleRegistry.register(rule)
        yield
    finally:
        RankingRuleRegistry._rules = original


def _apartment() -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id="apt-1", platform_id="p1", platform_listing_id="l1", title="Test", url="u",
        current_price=1000, current_status="available", first_seen_at=now, last_seen_at=now,
    )


class RenormalizationTests(unittest.TestCase):
    def test_a_single_evidenced_rule_gets_the_full_score(self) -> None:
        with _isolated_rules(_FixedRule("a", 0.8, 1.0)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertAlmostEqual(result.final_score, 80.0)

    def test_missing_evidence_does_not_drag_down_the_score(self) -> None:
        """Two rules, evenly weighted; only one has evidence — the final score must
        reflect 100% of the evidenced rule's raw_score, not 50%, since the missing
        rule is excluded from the weight-normalization denominator entirely.
        """
        with _isolated_rules(_FixedRule("a", 0.8, 1.0), _FixedRule("b", None, None)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 50, "b": 50}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertAlmostEqual(result.final_score, 80.0)

    def test_two_evidenced_rules_are_weighted_proportionally(self) -> None:
        with _isolated_rules(_FixedRule("a", 1.0, 1.0), _FixedRule("b", 0.0, 1.0)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 75, "b": 25}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertAlmostEqual(result.final_score, 75.0)

    def test_no_evidence_anywhere_scores_zero_and_warns(self) -> None:
        with _isolated_rules(_FixedRule("a", None, None), _FixedRule("b", None, None)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 50, "b": 50}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertEqual(result.final_score, 0.0)
        self.assertTrue(any("no weighted evidence" in w.lower() for w in result.warnings))

    def test_a_rule_with_zero_configured_weight_still_runs_and_appears(self) -> None:
        with _isolated_rules(_FixedRule("a", 0.9, 1.0), _FixedRule("b", 0.1, 1.0)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))  # "b" unconfigured -> weight 0
            result = pipeline.rank_one(_apartment(), RankingContext())
        rule_keys = [c.rule_key for c in result.contributions]
        self.assertIn("b", rule_keys)
        b_contribution = next(c for c in result.contributions if c.rule_key == "b")
        self.assertEqual(b_contribution.weight, 0.0)
        self.assertAlmostEqual(result.final_score, 90.0)  # "b" contributes nothing


class ConfidenceTests(unittest.TestCase):
    def test_overall_confidence_is_the_weighted_average_of_contributing_rules(self) -> None:
        with _isolated_rules(_FixedRule("a", 1.0, 1.0), _FixedRule("b", 1.0, 0.4)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 50, "b": 50}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertAlmostEqual(result.confidence.overall, 0.7)  # (1.0*0.5 + 0.4*0.5)

    def test_confidence_is_none_when_nothing_contributed(self) -> None:
        with _isolated_rules(_FixedRule("a", None, None)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertIsNone(result.confidence.overall)

    def test_per_rule_confidence_includes_every_rule_even_without_evidence(self) -> None:
        with _isolated_rules(_FixedRule("a", 1.0, 1.0), _FixedRule("b", None, None)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertEqual(result.confidence.per_rule, {"a": 1.0, "b": None})


class ExplanationTests(unittest.TestCase):
    def test_high_scoring_rules_become_positive_factors(self) -> None:
        with _isolated_rules(_FixedRule("a", 0.95, 1.0, detail="Excellent thing")):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertIn("Excellent thing", result.explanation.top_positive_factors)
        self.assertEqual(result.explanation.top_negative_factors, [])

    def test_low_scoring_rules_become_negative_factors(self) -> None:
        with _isolated_rules(_FixedRule("a", 0.05, 1.0, detail="Terrible thing")):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertIn("Terrible thing", result.explanation.top_negative_factors)
        self.assertEqual(result.explanation.top_positive_factors, [])

    def test_positive_factors_are_sorted_by_weighted_contribution_descending(self) -> None:
        with _isolated_rules(
            _FixedRule("a", 0.7, 1.0, detail="Modest positive"),
            _FixedRule("b", 0.9, 1.0, detail="Strong positive"),
        ):
            pipeline = RankingPipeline(RankingWeights(values={"a": 50, "b": 50}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertEqual(result.explanation.top_positive_factors[0], "Strong positive")

    def test_no_detail_rules_are_excluded_from_explanation(self) -> None:
        with _isolated_rules(_FixedRule("a", 0.9, 1.0, detail=None)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertEqual(result.explanation.top_positive_factors, [])
        self.assertEqual(result.explanation.all_reasons, [])

    def test_explanation_carries_the_same_final_score_and_confidence(self) -> None:
        with _isolated_rules(_FixedRule("a", 0.8, 0.9, detail="Reason")):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertEqual(result.explanation.final_score, result.final_score)
        self.assertEqual(result.explanation.confidence, result.confidence)


class DeterminismTests(unittest.TestCase):
    def test_contributions_follow_registration_order(self) -> None:
        with _isolated_rules(_FixedRule("z", 0.5, 1.0), _FixedRule("a", 0.5, 1.0)):
            pipeline = RankingPipeline(RankingWeights(values={"z": 50, "a": 50}))
            result = pipeline.rank_one(_apartment(), RankingContext())
        self.assertEqual([c.rule_key for c in result.contributions], ["z", "a"])

    def test_running_the_same_apartment_twice_gives_the_same_score(self) -> None:
        with _isolated_rules(_FixedRule("a", 0.73, 1.0)):
            pipeline = RankingPipeline(RankingWeights(values={"a": 100}))
            result1 = pipeline.rank_one(_apartment(), RankingContext())
            result2 = pipeline.rank_one(_apartment(), RankingContext())
        self.assertEqual(result1.final_score, result2.final_score)


if __name__ == "__main__":
    unittest.main()
