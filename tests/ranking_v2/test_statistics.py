"""Unit tests for RankingStatistics — src/ranking_v2/statistics.py."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from src.ranking_v2.models import (
    RankedApartmentV2,
    RankingConfidence,
    RankingEvidence,
    RankingExplanation,
    RuleContribution,
)
from src.ranking_v2.statistics import compute_ranking_statistics

_NOW = datetime.now(timezone.utc)


def _ranked(apartment_id: str, score: float, confidence: float | None, rule_scores: dict) -> RankedApartmentV2:
    contributions = [
        RuleContribution(
            rule_key=key,
            evidence=RankingEvidence(rule_key=key, raw_score=raw_score, confidence=confidence, detail="x"),
            weight=1.0 / len(rule_scores) if raw_score is not None else 0.0,
            weighted_score=(raw_score or 0.0) / len(rule_scores),
        )
        for key, raw_score in rule_scores.items()
    ]
    explanation = RankingExplanation(apartment_id=apartment_id, final_score=score, confidence=RankingConfidence(overall=confidence))
    return RankedApartmentV2(
        apartment_id=apartment_id, rank=0, final_score=score, confidence=RankingConfidence(overall=confidence),
        contributions=contributions, explanation=explanation, warnings=[], computed_at=_NOW,
    )


class RankingStatisticsTests(unittest.TestCase):
    def test_empty_ranked_list_is_honest(self) -> None:
        stats = compute_ranking_statistics([])
        self.assertEqual(stats.total_apartments, 0)
        self.assertIsNone(stats.average_score)
        self.assertIsNone(stats.average_confidence)

    def test_average_score_and_confidence(self) -> None:
        ranked = [
            _ranked("a1", 80.0, 1.0, {"price": 0.8}),
            _ranked("a2", 60.0, 0.5, {"price": 0.6}),
        ]
        stats = compute_ranking_statistics(ranked)
        self.assertAlmostEqual(stats.average_score, 70.0)
        self.assertAlmostEqual(stats.average_confidence, 0.75)

    def test_rule_coverage_reflects_evidence_presence(self) -> None:
        ranked = [
            _ranked("a1", 80.0, 1.0, {"price": 0.8, "walking_distance": None}),
            _ranked("a2", 60.0, 1.0, {"price": 0.6, "walking_distance": 0.5}),
        ]
        stats = compute_ranking_statistics(ranked)
        self.assertEqual(stats.rule_coverage["price"], 1.0)
        self.assertEqual(stats.rule_coverage["walking_distance"], 0.5)

    def test_average_score_by_rule_only_counts_evidenced_apartments(self) -> None:
        ranked = [
            _ranked("a1", 80.0, 1.0, {"walking_distance": None}),
            _ranked("a2", 60.0, 1.0, {"walking_distance": 0.4}),
        ]
        stats = compute_ranking_statistics(ranked)
        self.assertAlmostEqual(stats.average_score_by_rule["walking_distance"], 0.4)

    def test_as_dict_is_json_safe(self) -> None:
        stats = compute_ranking_statistics([_ranked("a1", 80.0, 1.0, {"price": 0.8})])
        json.dumps(stats.as_dict())  # must not raise


if __name__ == "__main__":
    unittest.main()
