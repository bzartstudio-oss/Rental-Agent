"""Unit tests for RankingProfile + the two built-in profiles — src/ranking_v2/profile.py."""

from __future__ import annotations

import unittest

from src.ranking_v2.profile import COMPREHENSIVE_PROFILE, DEFAULT_PROFILE, RankingProfile
from src.ranking_v2.registry import RankingRuleRegistry
from src.ranking_v2.weights import RankingWeights


class RankingProfileTests(unittest.TestCase):
    def test_default_profile_matches_the_missions_own_worked_example(self) -> None:
        normalized = DEFAULT_PROFILE.weights.normalized()
        self.assertAlmostEqual(normalized["price"], 0.40)
        self.assertAlmostEqual(normalized["walking_distance"], 0.25)
        self.assertAlmostEqual(normalized["availability"], 0.15)
        self.assertAlmostEqual(normalized["public_transport"], 0.10)
        self.assertAlmostEqual(normalized["lifestyle"], 0.10)

    def test_comprehensive_profile_covers_every_registered_rule(self) -> None:
        registered_keys = {rule.rule_key for rule in RankingRuleRegistry.all()}
        self.assertEqual(set(COMPREHENSIVE_PROFILE.weights.values.keys()), registered_keys)

    def test_comprehensive_profile_weighs_every_rule_equally(self) -> None:
        normalized = COMPREHENSIVE_PROFILE.weights.normalized()
        values = list(normalized.values())
        self.assertTrue(all(abs(v - values[0]) < 1e-9 for v in values))

    def test_a_custom_profile_can_be_built_directly(self) -> None:
        profile = RankingProfile(name="custom", weights=RankingWeights(values={"price": 100}))
        self.assertEqual(profile.weights.normalized(), {"price": 1.0})


if __name__ == "__main__":
    unittest.main()
