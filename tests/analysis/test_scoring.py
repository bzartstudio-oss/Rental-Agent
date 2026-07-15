"""Unit tests for src/analysis/scoring.py — configurable composite scoring."""

import unittest
from datetime import datetime, timezone

from src.analysis.models import AnalyzerResult
from src.analysis.scoring import (
    CompositeScoreDefinition,
    ScoringConfiguration,
    compute_composite_scores,
    default_scoring_configuration,
)


def _result(analyzer_name: str, score, confidence=1.0) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer_name=analyzer_name, apartment_id="apt-1", score=score, confidence=confidence,
        evidence=[], warnings=[], computed_at=datetime.now(timezone.utc), version="1.0.0", source="test",
    )


class ComputeCompositeScoresTests(unittest.TestCase):
    def test_simple_weighted_average(self) -> None:
        config = ScoringConfiguration(
            composites=[CompositeScoreDefinition(name="test_composite", weights={"a": 0.5, "b": 0.5})],
            overall_weights={"test_composite": 1.0},
        )
        results = [_result("a", 1.0), _result("b", 0.0)]

        composites = compute_composite_scores(results, config)
        test_composite = next(c for c in composites if c.name == "test_composite")

        self.assertEqual(test_composite.score, 0.5)

    def test_missing_component_is_excluded_not_treated_as_zero(self) -> None:
        config = ScoringConfiguration(
            composites=[CompositeScoreDefinition(name="test_composite", weights={"a": 0.5, "b": 0.5})],
            overall_weights={"test_composite": 1.0},
        )
        results = [_result("a", 1.0)]  # "b" never ran

        composites = compute_composite_scores(results, config)
        test_composite = next(c for c in composites if c.name == "test_composite")

        self.assertEqual(test_composite.score, 1.0)  # average over "a" alone, not (1.0+0)/2

    def test_no_evidence_composite_is_none_not_zero(self) -> None:
        config = ScoringConfiguration(
            composites=[CompositeScoreDefinition(name="test_composite", weights={"a": 1.0})],
            overall_weights={"test_composite": 1.0},
        )
        results = [_result("a", None)]  # "a" ran but had no evidence

        composites = compute_composite_scores(results, config)
        test_composite = next(c for c in composites if c.name == "test_composite")

        self.assertIsNone(test_composite.score)

    def test_confidence_weights_the_contribution(self) -> None:
        config = ScoringConfiguration(
            composites=[CompositeScoreDefinition(name="test_composite", weights={"a": 0.5, "b": 0.5})],
            overall_weights={"test_composite": 1.0},
        )
        # "a" is high-confidence and low-scoring; "b" is low-confidence and high-scoring —
        # "a" should dominate the average.
        results = [_result("a", 0.0, confidence=1.0), _result("b", 1.0, confidence=0.1)]

        composites = compute_composite_scores(results, config)
        test_composite = next(c for c in composites if c.name == "test_composite")

        self.assertLess(test_composite.score, 0.2)

    def test_overall_score_averages_the_composites(self) -> None:
        config = ScoringConfiguration(
            composites=[
                CompositeScoreDefinition(name="one", weights={"a": 1.0}),
                CompositeScoreDefinition(name="two", weights={"b": 1.0}),
            ],
            overall_weights={"one": 0.5, "two": 0.5},
        )
        results = [_result("a", 1.0), _result("b", 0.0)]

        composites = compute_composite_scores(results, config)
        overall = next(c for c in composites if c.name == "overall_analysis_score")

        self.assertEqual(overall.score, 0.5)

    def test_overall_score_is_none_when_no_composite_has_evidence(self) -> None:
        config = ScoringConfiguration(
            composites=[CompositeScoreDefinition(name="one", weights={"a": 1.0})],
            overall_weights={"one": 1.0},
        )
        results = [_result("a", None)]

        composites = compute_composite_scores(results, config)
        overall = next(c for c in composites if c.name == "overall_analysis_score")

        self.assertIsNone(overall.score)

    def test_default_configuration_defines_all_four_named_composites(self) -> None:
        config = default_scoring_configuration()
        names = {c.name for c in config.composites}
        self.assertEqual(names, {"location_score", "convenience_score", "lifestyle_score", "accessibility_score"})
        self.assertEqual(set(config.overall_weights), names)

    def test_scoring_is_configurable_not_hardcoded(self) -> None:
        """A caller can supply a completely different weighting scheme and the
        computation reflects it — proving the weights are data, not baked into
        compute_composite_scores itself.
        """
        custom_config = ScoringConfiguration(
            composites=[CompositeScoreDefinition(name="custom", weights={"a": 1.0})],
            overall_weights={"custom": 1.0},
        )
        results = [_result("a", 0.42)]

        composites = compute_composite_scores(results, custom_config)

        self.assertEqual([c.name for c in composites], ["custom", "overall_analysis_score"])
        self.assertEqual(next(c for c in composites if c.name == "custom").score, 0.42)


if __name__ == "__main__":
    unittest.main()
