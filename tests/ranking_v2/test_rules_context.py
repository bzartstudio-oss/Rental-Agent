"""Unit tests for FilterPreferenceRankingRule/AnalysisCompositeRankingRule/
ProviderHealthRankingRule/SearchHistoryRankingRule — src/ranking_v2/rules/context_rules.py.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.analysis.models import AnalysisResult, CompositeScore
from src.filter_engine.result import FilterResult
from src.providers.health import ProviderHealth
from src.ranking_v2.base_rule import RankingContext
from src.ranking_v2.rules.context_rules import (
    AnalysisCompositeRankingRule,
    FilterPreferenceRankingRule,
    ProviderHealthRankingRule,
    SearchHistoryRankingRule,
)
from src.search_memory.models import ApartmentPriceChange, PlatformCoverageChange, SearchComparison
from src.storage.models import Apartment

_NOW = datetime.now(timezone.utc)


def _apartment() -> Apartment:
    return Apartment(
        id="apt-1", platform_id="p1", platform_listing_id="l1", title="Test", url="u",
        current_price=1000, current_status="available", first_seen_at=_NOW, last_seen_at=_NOW,
    )


class FilterPreferenceRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = FilterPreferenceRankingRule()

    def test_no_filter_results_is_honest_no_evidence(self) -> None:
        evidence = self.rule.evaluate(_apartment(), RankingContext())
        self.assertIsNone(evidence.raw_score)

    def test_matches_fraction_of_preference_filters(self) -> None:
        result = FilterResult(apartment_id="apt-1", matches=True, per_filter={"a": True, "b": True, "c": False})
        context = RankingContext(filter_results={"apt-1": result})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertAlmostEqual(evidence.raw_score, 2 / 3)
        self.assertIn("2/3", evidence.detail)


class AnalysisCompositeRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = AnalysisCompositeRankingRule()

    def test_no_analysis_results_is_honest_no_evidence(self) -> None:
        evidence = self.rule.evaluate(_apartment(), RankingContext())
        self.assertIsNone(evidence.raw_score)

    def test_composite_with_no_evidence_anywhere_is_honest_no_evidence(self) -> None:
        result = AnalysisResult(
            apartment_id="apt-1", search_id=None, computed_at=_NOW,
            analyzer_results=[], composite_scores=[CompositeScore(name="location_score", score=None, component_analyzer_names=[])],
        )
        context = RankingContext(analysis_results={"apt-1": result})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertIsNone(evidence.raw_score)

    def test_averages_composite_scores_with_evidence(self) -> None:
        result = AnalysisResult(
            apartment_id="apt-1", search_id=None, computed_at=_NOW,
            analyzer_results=[],
            composite_scores=[
                CompositeScore(name="location_score", score=0.8, component_analyzer_names=[]),
                CompositeScore(name="value_score", score=0.4, component_analyzer_names=[]),
            ],
        )
        context = RankingContext(analysis_results={"apt-1": result})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertAlmostEqual(evidence.raw_score, 0.6)
        self.assertEqual(evidence.confidence, 0.7)


class ProviderHealthRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = ProviderHealthRankingRule()

    def test_no_provider_health_is_honest_no_evidence(self) -> None:
        evidence = self.rule.evaluate(_apartment(), RankingContext())
        self.assertIsNone(evidence.raw_score)

    def test_available_provider_scores_the_maximum(self) -> None:
        health = ProviderHealth(provider_id="x", is_available_now=True, platform_id="p1", connector_health=None)
        context = RankingContext(provider_health={"p1": health})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertEqual(evidence.raw_score, 1.0)

    def test_unavailable_provider_scores_zero(self) -> None:
        health = ProviderHealth(provider_id="x", is_available_now=False, platform_id="p1", connector_health=None)
        context = RankingContext(provider_health={"p1": health})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertEqual(evidence.raw_score, 0.0)


class SearchHistoryRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = SearchHistoryRankingRule()

    def test_no_comparison_is_honest_no_evidence(self) -> None:
        evidence = self.rule.evaluate(_apartment(), RankingContext())
        self.assertIsNone(evidence.raw_score)

    def _comparison(self, **kwargs) -> SearchComparison:
        defaults = dict(
            previous_search_id="s0", current_search_id="s1", new_apartment_ids=[], removed_apartment_ids=[],
            changed_apartment_ids=[], price_changes=[], availability_changes=[], connector_failures=[],
            platform_coverage_change=PlatformCoverageChange(
                newly_searched_platform_ids=[], no_longer_searched_platform_ids=[]
            ),
            execution_time_delta_ms=None, search_quality_delta=None,
        )
        defaults.update(kwargs)
        return SearchComparison(**defaults)

    def test_price_drop_scores_well(self) -> None:
        comparison = self._comparison(price_changes=[ApartmentPriceChange(apartment_id="apt-1", old_price=1200, new_price=1000)])
        context = RankingContext(search_comparison=comparison)
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertEqual(evidence.raw_score, 1.0)

    def test_price_rise_scores_zero(self) -> None:
        comparison = self._comparison(price_changes=[ApartmentPriceChange(apartment_id="apt-1", old_price=1000, new_price=1200)])
        context = RankingContext(search_comparison=comparison)
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertEqual(evidence.raw_score, 0.0)

    def test_newly_discovered_apartment_scores_neutral(self) -> None:
        comparison = self._comparison(new_apartment_ids=["apt-1"])
        context = RankingContext(search_comparison=comparison)
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertEqual(evidence.raw_score, 0.6)

    def test_apartment_absent_from_comparison_is_honest_no_evidence(self) -> None:
        comparison = self._comparison()
        context = RankingContext(search_comparison=comparison)
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertIsNone(evidence.raw_score)


if __name__ == "__main__":
    unittest.main()
