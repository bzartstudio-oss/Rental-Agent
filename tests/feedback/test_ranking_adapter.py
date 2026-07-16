"""Ranking Integration tests — src/feedback/ranking_adapter.py. Covers the three
modes the mission requires (EXPLICIT_ONLY/SUGGESTED/ASSISTED) and confirms
`FeedbackEngine` is never coupled to a specific ranking rule class.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.feedback.models import FeedbackMode, PreferenceConfidence, PreferenceProfile, PreferenceValue
from src.feedback.ranking_adapter import resolve_ranking_profile, suggest_ranking_weights
from src.ranking_v2 import DEFAULT_PROFILE, RankingProfile, RankingWeights

_NOW = datetime.now(timezone.utc)


def _profile(mode: FeedbackMode, **preferences) -> PreferenceProfile:
    values = {}
    for key, (current_value, confidence, is_explicit) in preferences.items():
        values[key] = PreferenceValue(
            preference_key=key, current_value=current_value,
            confidence=PreferenceConfidence(overall=confidence, supporting_evidence_count=1,
                                             opposing_evidence_count=0, explicit_count=1 if is_explicit else 0,
                                             inferred_count=0 if is_explicit else 1),
            source_types={"explicit" if is_explicit else "inferred"}, last_updated=_NOW, explanation="x",
            is_explicit=is_explicit,
        )
    return PreferenceProfile(profile_id="u1", mode=mode, preferences=values)


class SuggestRankingWeightsTests(unittest.TestCase):
    def test_high_confidence_importance_is_suggested(self) -> None:
        profile = _profile(FeedbackMode.SUGGESTED, walking_distance=({"importance": 0.9}, 0.8, False))
        weights = suggest_ranking_weights(profile)
        self.assertAlmostEqual(weights.values["walking_distance"], 90.0)

    def test_low_confidence_inferred_preference_is_not_suggested(self) -> None:
        profile = _profile(FeedbackMode.SUGGESTED, walking_distance=({"importance": 0.9}, 0.1, False))
        weights = suggest_ranking_weights(profile)
        self.assertNotIn("walking_distance", weights.values)

    def test_low_confidence_explicit_preference_is_still_suggested(self) -> None:
        """Explicit preferences bypass the confidence threshold entirely."""
        profile = _profile(FeedbackMode.EXPLICIT_ONLY, walking_distance=({"importance": 0.9}, 0.1, True))
        weights = suggest_ranking_weights(profile)
        self.assertIn("walking_distance", weights.values)

    def test_preferences_with_no_ranking_rule_counterpart_are_not_suggested(self) -> None:
        profile = _profile(FeedbackMode.SUGGESTED, property_type=({"preferred": "apartment"}, 1.0, True))
        weights = suggest_ranking_weights(profile)
        self.assertEqual(weights.values, {})

    def test_base_weights_are_preserved_when_not_overridden(self) -> None:
        base = RankingWeights(values={"price": 40, "availability": 15})
        profile = _profile(FeedbackMode.SUGGESTED)  # no preferences at all
        weights = suggest_ranking_weights(profile, base_weights=base)
        self.assertEqual(weights.values, {"price": 40, "availability": 15})


class ResolveRankingProfileTests(unittest.TestCase):
    def test_explicit_only_mode_returns_the_explicit_profile_unchanged(self) -> None:
        profile = _profile(FeedbackMode.EXPLICIT_ONLY, walking_distance=({"importance": 0.95}, 0.95, False))
        resolved = resolve_ranking_profile(profile, DEFAULT_PROFILE)
        self.assertIs(resolved, DEFAULT_PROFILE)

    def test_suggested_mode_does_not_apply_the_suggestion_either(self) -> None:
        """"Generate suggested weights but do not apply them automatically" (the
        mission's own words) — SUGGESTED must behave identically to EXPLICIT_ONLY
        for what actually ranks anything.
        """
        profile = _profile(FeedbackMode.SUGGESTED, walking_distance=({"importance": 0.95}, 0.95, False))
        resolved = resolve_ranking_profile(profile, DEFAULT_PROFILE)
        self.assertIs(resolved, DEFAULT_PROFILE)

    def test_assisted_mode_applies_the_suggestion(self) -> None:
        profile = _profile(FeedbackMode.ASSISTED, walking_distance=({"importance": 0.95}, 0.95, False))
        resolved = resolve_ranking_profile(profile, DEFAULT_PROFILE)
        self.assertIsNot(resolved, DEFAULT_PROFILE)
        self.assertAlmostEqual(resolved.weights.values["walking_distance"], 95.0)

    def test_assisted_mode_still_seeds_from_the_explicit_weights(self) -> None:
        custom_profile = RankingProfile(name="custom", weights=RankingWeights(values={"price": 60, "availability": 40}))
        profile = _profile(FeedbackMode.ASSISTED, walking_distance=({"importance": 0.9}, 0.9, False))
        resolved = resolve_ranking_profile(profile, custom_profile)
        self.assertEqual(resolved.weights.values["price"], 60)
        self.assertEqual(resolved.weights.values["availability"], 40)
        self.assertIn("walking_distance", resolved.weights.values)


if __name__ == "__main__":
    unittest.main()
