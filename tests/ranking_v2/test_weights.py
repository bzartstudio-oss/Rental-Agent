"""Weight tests for RankingWeights — src/ranking_v2/weights.py."""

from __future__ import annotations

import unittest

from src.ranking_v2.exceptions import RankingConfigurationError
from src.ranking_v2.weights import RankingWeights


class RankingWeightsTests(unittest.TestCase):
    def test_negative_weight_raises_configuration_error(self) -> None:
        with self.assertRaises(RankingConfigurationError):
            RankingWeights(values={"price": -1})

    def test_get_returns_zero_for_an_unconfigured_key(self) -> None:
        weights = RankingWeights(values={"price": 40})
        self.assertEqual(weights.get("walking_distance"), 0.0)

    def test_normalized_sums_to_one(self) -> None:
        weights = RankingWeights(values={"price": 40, "walking_distance": 25, "availability": 15,
                                          "public_transport": 10, "lifestyle": 10})
        normalized = weights.normalized()
        self.assertAlmostEqual(sum(normalized.values()), 1.0)

    def test_normalized_matches_the_missions_own_percentages(self) -> None:
        weights = RankingWeights(values={"price": 40, "walking_distance": 25, "availability": 15,
                                          "public_transport": 10, "lifestyle": 10})
        normalized = weights.normalized()
        self.assertAlmostEqual(normalized["price"], 0.40)
        self.assertAlmostEqual(normalized["walking_distance"], 0.25)
        self.assertAlmostEqual(normalized["availability"], 0.15)

    def test_empty_weights_normalize_to_empty(self) -> None:
        weights = RankingWeights(values={})
        self.assertEqual(weights.normalized(), {})

    def test_all_zero_weights_normalize_to_all_zero_not_a_crash(self) -> None:
        weights = RankingWeights(values={"price": 0, "availability": 0})
        normalized = weights.normalized()
        self.assertEqual(normalized, {"price": 0.0, "availability": 0.0})


if __name__ == "__main__":
    unittest.main()
