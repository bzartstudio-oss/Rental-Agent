"""Confidence tests for the shared decay/confidence math — src/feedback/decay.py.
Covers exactly the properties the mission's own "Learning Rules" section demands:
a single action must not strongly alter the profile, conflicting behavior reduces
confidence, explicit counts more than inferred, and recent behavior may be
weighted more than old behavior (configurably).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.feedback.decay import DecayConfig, compute_confidence, decayed_weight
from src.feedback.models import PreferenceObservation

_NOW = datetime.now(timezone.utc)


def _obs(direction: str, source_type: str, magnitude: float = 1.0, age_days: float = 0.0) -> PreferenceObservation:
    return PreferenceObservation(
        profile_id="u1", preference_key="x", event_id="e", direction=direction, magnitude=magnitude,
        source_type=source_type, computed_at=_NOW - timedelta(days=age_days), explanation="x",
    )


class SingleActionTests(unittest.TestCase):
    def test_one_inferred_observation_gives_low_confidence(self) -> None:
        confidence = compute_confidence([_obs("supporting", "inferred")], _NOW, DecayConfig())
        self.assertLess(confidence.overall, 0.3)

    def test_one_explicit_observation_still_stays_under_full_confidence(self) -> None:
        """"A single action must not strongly alter the profile" (the mission's own
        words) — even an explicit action, weighted more heavily, must not reach 1.0
        confidence alone.
        """
        confidence = compute_confidence([_obs("supporting", "explicit")], _NOW, DecayConfig())
        self.assertLess(confidence.overall, 1.0)
        self.assertGreater(confidence.overall, 0.3)  # still meaningfully more trusted than a lone inferred one


class ConflictTests(unittest.TestCase):
    def test_conflicting_observations_reduce_confidence_toward_zero(self) -> None:
        observations = [_obs("supporting", "inferred") for _ in range(3)] + [_obs("opposing", "inferred") for _ in range(3)]
        confidence = compute_confidence(observations, _NOW, DecayConfig())
        self.assertLess(confidence.overall, 0.1)

    def test_consistent_observations_build_higher_confidence_than_conflicting(self) -> None:
        consistent = [_obs("supporting", "inferred") for _ in range(4)]
        conflicting = [_obs("supporting", "inferred") for _ in range(2)] + [_obs("opposing", "inferred") for _ in range(2)]
        confidence_consistent = compute_confidence(consistent, _NOW, DecayConfig())
        confidence_conflicting = compute_confidence(conflicting, _NOW, DecayConfig())
        self.assertGreater(confidence_consistent.overall, confidence_conflicting.overall)


class RepetitionTests(unittest.TestCase):
    def test_repeated_consistent_events_strengthen_confidence(self) -> None:
        few = [_obs("supporting", "inferred") for _ in range(2)]
        many = [_obs("supporting", "inferred") for _ in range(10)]
        confidence_few = compute_confidence(few, _NOW, DecayConfig())
        confidence_many = compute_confidence(many, _NOW, DecayConfig())
        self.assertGreater(confidence_many.overall, confidence_few.overall)

    def test_confidence_saturates_rather_than_growing_unbounded(self) -> None:
        many = [_obs("supporting", "inferred") for _ in range(1000)]
        confidence = compute_confidence(many, _NOW, DecayConfig())
        self.assertLessEqual(confidence.overall, 1.0)


class DecayTests(unittest.TestCase):
    def test_recent_observation_weighs_more_than_an_old_one(self) -> None:
        config = DecayConfig(half_life_days=10.0)
        recent = decayed_weight(_obs("supporting", "inferred", age_days=0), _NOW, config)
        old = decayed_weight(_obs("supporting", "inferred", age_days=30), _NOW, config)
        self.assertGreater(recent, old)

    def test_half_life_is_configurable(self) -> None:
        short_half_life = DecayConfig(half_life_days=1.0)
        long_half_life = DecayConfig(half_life_days=100.0)
        obs = _obs("supporting", "inferred", age_days=10)
        weight_short = decayed_weight(obs, _NOW, short_half_life)
        weight_long = decayed_weight(obs, _NOW, long_half_life)
        self.assertLess(weight_short, weight_long)

    def test_explicit_weighs_more_than_inferred_at_the_same_age(self) -> None:
        config = DecayConfig()
        explicit_weight = decayed_weight(_obs("supporting", "explicit"), _NOW, config)
        inferred_weight = decayed_weight(_obs("supporting", "inferred"), _NOW, config)
        self.assertGreater(explicit_weight, inferred_weight)


class EmptyEvidenceTests(unittest.TestCase):
    def test_no_observations_gives_honest_zero_confidence(self) -> None:
        confidence = compute_confidence([], _NOW, DecayConfig())
        self.assertEqual(confidence.overall, 0.0)
        self.assertEqual(confidence.supporting_evidence_count, 0)
        self.assertEqual(confidence.opposing_evidence_count, 0)


if __name__ == "__main__":
    unittest.main()
