"""Unit tests for the 4 shared `aggregate()` implementations —
src/feedback/base_rule.py.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.feedback.base_rule import (
    BooleanPreferenceRule,
    CategoricalPreferenceRule,
    ImportancePreferenceRule,
    PreferenceContext,
    ThresholdPreferenceRule,
)
from src.feedback.models import PreferenceObservation

_NOW = datetime.now(timezone.utc)


class _Importance(ImportancePreferenceRule):
    preference_key = "x"

    def relevant_event_types(self):
        return frozenset()

    def observe(self, event, context):
        return None

    def metadata(self):
        return None


class _Threshold(ThresholdPreferenceRule):
    preference_key = "x"

    def relevant_event_types(self):
        return frozenset()

    def observe(self, event, context):
        return None

    def metadata(self):
        return None


class _Categorical(CategoricalPreferenceRule):
    preference_key = "x"

    def relevant_event_types(self):
        return frozenset()

    def observe(self, event, context):
        return None

    def metadata(self):
        return None


class _Boolean(BooleanPreferenceRule):
    preference_key = "x"

    def relevant_event_types(self):
        return frozenset()

    def observe(self, event, context):
        return None

    def metadata(self):
        return None


def _obs(direction, source_type="inferred", observed_value=None) -> PreferenceObservation:
    return PreferenceObservation(
        profile_id="u1", preference_key="x", event_id="e", direction=direction, magnitude=1.0,
        source_type=source_type, computed_at=_NOW, explanation="x", observed_value=observed_value,
    )


class ImportanceAggregationTests(unittest.TestCase):
    def test_no_observations_is_honest_no_evidence(self) -> None:
        value = _Importance().aggregate([], PreferenceContext(now=_NOW))
        self.assertIsNone(value.current_value)
        self.assertEqual(value.confidence.overall, 0.0)

    def test_all_supporting_gives_importance_near_one(self) -> None:
        value = _Importance().aggregate([_obs("supporting"), _obs("supporting")], PreferenceContext(now=_NOW))
        self.assertAlmostEqual(value.current_value["importance"], 1.0)

    def test_all_opposing_gives_importance_near_zero(self) -> None:
        value = _Importance().aggregate([_obs("opposing"), _obs("opposing")], PreferenceContext(now=_NOW))
        self.assertAlmostEqual(value.current_value["importance"], 0.0)

    def test_mixed_gives_importance_near_the_middle(self) -> None:
        value = _Importance().aggregate([_obs("supporting"), _obs("opposing")], PreferenceContext(now=_NOW))
        self.assertAlmostEqual(value.current_value["importance"], 0.5)


class ThresholdAggregationTests(unittest.TestCase):
    def test_no_numeric_observations_is_honest_no_evidence(self) -> None:
        value = _Threshold().aggregate([], PreferenceContext(now=_NOW))
        self.assertIsNone(value.current_value)

    def test_weighted_average_of_observed_values(self) -> None:
        observations = [_obs("supporting", observed_value={"value": 1000.0}), _obs("supporting", observed_value={"value": 2000.0})]
        value = _Threshold().aggregate(observations, PreferenceContext(now=_NOW))
        self.assertAlmostEqual(value.current_value["preferred"], 1500.0, delta=50)


class CategoricalAggregationTests(unittest.TestCase):
    def test_no_categorical_observations_is_honest_no_evidence(self) -> None:
        value = _Categorical().aggregate([], PreferenceContext(now=_NOW))
        self.assertIsNone(value.current_value)

    def test_leading_category_by_weighted_support(self) -> None:
        observations = [
            _obs("supporting", observed_value={"category": "apartment"}),
            _obs("supporting", observed_value={"category": "apartment"}),
            _obs("supporting", observed_value={"category": "studio"}),
        ]
        value = _Categorical().aggregate(observations, PreferenceContext(now=_NOW))
        self.assertEqual(value.current_value["preferred"], "apartment")
        self.assertIn("studio", value.current_value["distribution"])

    def test_opposing_categorical_observations_are_ignored_not_subtracted(self) -> None:
        observations = [_obs("opposing", observed_value={"category": "studio"})]
        value = _Categorical().aggregate(observations, PreferenceContext(now=_NOW))
        self.assertIsNone(value.current_value)


class BooleanAggregationTests(unittest.TestCase):
    def test_no_observations_is_honest_no_evidence(self) -> None:
        value = _Boolean().aggregate([], PreferenceContext(now=_NOW))
        self.assertIsNone(value.current_value)

    def test_more_supporting_than_opposing_wants_true(self) -> None:
        value = _Boolean().aggregate([_obs("supporting"), _obs("supporting"), _obs("opposing")], PreferenceContext(now=_NOW))
        self.assertTrue(value.current_value["wants"])

    def test_more_opposing_than_supporting_wants_false(self) -> None:
        value = _Boolean().aggregate([_obs("opposing"), _obs("opposing"), _obs("supporting")], PreferenceContext(now=_NOW))
        self.assertFalse(value.current_value["wants"])


if __name__ == "__main__":
    unittest.main()
