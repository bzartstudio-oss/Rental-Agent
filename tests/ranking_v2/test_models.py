"""Unit tests for the shared ranking data shapes — src/ranking_v2/models.py."""

from __future__ import annotations

import unittest

from src.ranking_v2.models import RankingConfidence, RankingEvidence, RankingExplanation


class RankingEvidenceTests(unittest.TestCase):
    def test_warnings_default_to_empty_list_not_none(self) -> None:
        evidence = RankingEvidence(rule_key="price", raw_score=0.5, confidence=1.0, detail="x")
        self.assertEqual(evidence.warnings, [])

    def test_two_instances_do_not_share_mutable_defaults(self) -> None:
        e1 = RankingEvidence(rule_key="a", raw_score=None, confidence=None, detail=None)
        e2 = RankingEvidence(rule_key="b", raw_score=None, confidence=None, detail=None)
        e1.warnings.append("oops")
        self.assertEqual(e2.warnings, [])


class RankingConfidenceTests(unittest.TestCase):
    def test_defaults_are_empty_not_none(self) -> None:
        confidence = RankingConfidence(overall=None)
        self.assertEqual(confidence.per_rule, {})


class RankingExplanationTests(unittest.TestCase):
    def test_defaults_are_empty_lists_not_none(self) -> None:
        explanation = RankingExplanation(apartment_id="a1", final_score=50.0, confidence=RankingConfidence(overall=None))
        self.assertEqual(explanation.top_positive_factors, [])
        self.assertEqual(explanation.top_negative_factors, [])
        self.assertEqual(explanation.all_reasons, [])


if __name__ == "__main__":
    unittest.main()
