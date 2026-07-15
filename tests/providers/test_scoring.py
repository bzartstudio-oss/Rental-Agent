"""Unit tests for the pure scoring function — src/providers/scoring.py."""

from __future__ import annotations

import unittest

from src.providers.scoring import ProviderMetadata, ScoringWeights, score_provider


class ScoreProviderTests(unittest.TestCase):
    def test_unavailable_provider_scores_zero_on_availability_component(self) -> None:
        metadata = ProviderMetadata(provider_id="x", cost_score=0.0, freshness_score=1.0, quality_score=1.0)

        score = score_provider(metadata, available=False)

        self.assertEqual(score.availability_component, 0.0)

    def test_available_provider_scores_full_availability_weight(self) -> None:
        metadata = ProviderMetadata(provider_id="x", cost_score=0.0, freshness_score=0.0, quality_score=0.0)
        weights = ScoringWeights(availability=0.1, cost=0.0, freshness=0.0, quality=0.0)

        score = score_provider(metadata, available=True, weights=weights)

        self.assertAlmostEqual(score.availability_component, 0.1)
        self.assertAlmostEqual(score.total, 0.1)

    def test_cost_is_inverted_lower_cost_scores_higher(self) -> None:
        weights = ScoringWeights(availability=0.0, cost=1.0, freshness=0.0, quality=0.0)
        cheap = ProviderMetadata(provider_id="cheap", cost_score=0.0, freshness_score=0.0, quality_score=0.0)
        expensive = ProviderMetadata(provider_id="expensive", cost_score=1.0, freshness_score=0.0, quality_score=0.0)

        cheap_score = score_provider(cheap, available=True, weights=weights)
        expensive_score = score_provider(expensive, available=True, weights=weights)

        self.assertGreater(cheap_score.total, expensive_score.total)

    def test_freshness_and_quality_score_higher_is_better(self) -> None:
        weights = ScoringWeights(availability=0.0, cost=0.0, freshness=0.5, quality=0.5)
        fresh_high_quality = ProviderMetadata(provider_id="a", cost_score=0.0, freshness_score=1.0, quality_score=1.0)
        stale_low_quality = ProviderMetadata(provider_id="b", cost_score=0.0, freshness_score=0.0, quality_score=0.0)

        high = score_provider(fresh_high_quality, available=True, weights=weights)
        low = score_provider(stale_low_quality, available=True, weights=weights)

        self.assertGreater(high.total, low.total)

    def test_total_is_the_sum_of_its_components(self) -> None:
        metadata = ProviderMetadata(provider_id="x", cost_score=0.3, freshness_score=0.6, quality_score=0.9)

        score = score_provider(metadata, available=True)

        self.assertAlmostEqual(
            score.total,
            score.availability_component + score.cost_component + score.freshness_component + score.quality_component,
        )

    def test_default_weights_sum_to_one(self) -> None:
        weights = ScoringWeights()
        self.assertAlmostEqual(weights.availability + weights.cost + weights.freshness + weights.quality, 1.0)


if __name__ == "__main__":
    unittest.main()
