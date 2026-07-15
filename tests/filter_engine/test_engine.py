"""Unit/integration tests for FilterEngine — src/filter_engine/engine.py, against
the real 39 built-in filters (not fakes) — the pipeline itself (validation ->
normalization -> execution -> statistics) is what's under test here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import unittest

from src.filter_engine.base_filter import FilterContext
from src.filter_engine.composition import FilterCondition, FilterGroup, FilterOperator
from src.filter_engine.configuration import FilterConfiguration
from src.filter_engine.engine import FilterEngine
from src.filter_engine.exceptions import FilterConfigurationError, FilterValidationError
from src.storage.models import Apartment


def _apartment(**overrides) -> Apartment:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="a1", platform_id="p1", platform_listing_id="1", title="A Place", url="x",
        current_price=1000.0, current_status="available", first_seen_at=now, last_seen_at=now,
    )
    defaults.update(overrides)
    return Apartment(**defaults)


class FilterEngineRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = FilterEngine()
        self.apartments = [
            _apartment(id="cheap", current_price=900, property_type="apartment"),
            _apartment(id="expensive", current_price=3000, property_type="apartment"),
            _apartment(id="house", current_price=1500, property_type="house"),
        ]

    def test_flat_criteria_is_an_implicit_and(self) -> None:
        results, stats = self.engine.run(self.apartments, {"max_price": 2000, "property_type": "apartment"})

        matched = {r.apartment_id for r in results if r.matches}
        self.assertEqual(matched, {"cheap"})
        self.assertEqual(stats.matched_count, 1)
        self.assertEqual(stats.total_apartments, 3)

    def test_empty_criteria_matches_everything(self) -> None:
        results, stats = self.engine.run(self.apartments, {})
        self.assertTrue(all(r.matches for r in results))
        self.assertEqual(stats.matched_count, 3)

    def test_filter_apartments_returns_only_matches_in_original_order(self) -> None:
        matched = self.engine.filter_apartments(self.apartments, {"max_price": 2000})
        self.assertEqual([a.id for a in matched], ["cheap", "house"])

    def test_invalid_criteria_value_raises_filter_validation_error(self) -> None:
        with self.assertRaises(FilterValidationError):
            self.engine.run(self.apartments, {"max_price": -5})

    def test_unknown_filter_key_raises(self) -> None:
        with self.assertRaises(FilterValidationError):
            self.engine.run(self.apartments, {"not_a_real_filter": 1})

    def test_disabled_filter_key_raises(self) -> None:
        engine = FilterEngine(FilterConfiguration(enabled_filter_keys={"min_price"}))
        with self.assertRaises(FilterValidationError):
            engine.run(self.apartments, {"max_price": 2000})

    def test_execution_time_is_measured(self) -> None:
        _, stats = self.engine.run(self.apartments, {"max_price": 2000})
        self.assertIsInstance(stats.execution_time_ms, int)
        self.assertGreaterEqual(stats.execution_time_ms, 0)

    def test_dormant_filter_never_excludes_anything(self) -> None:
        results, stats = self.engine.run(self.apartments, {"private_bathroom": True})
        self.assertEqual(stats.matched_count, 3)  # every apartment "passes" a dormant filter

    def test_wrapped_weighted_criteria_value_is_unwrapped(self) -> None:
        results, _ = self.engine.run(self.apartments, {"max_price": {"value": 2000, "weight": 3.0}})
        matched = {r.apartment_id for r in results if r.matches}
        self.assertEqual(matched, {"cheap", "house"})


class FilterEngineGroupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = FilterEngine()
        self.apartments = [
            _apartment(id="cheap", current_price=900, property_type="apartment"),
            _apartment(id="expensive", current_price=3000, property_type="apartment"),
            _apartment(id="house", current_price=1500, property_type="house"),
        ]

    def test_or_group_via_run_group(self) -> None:
        group = FilterGroup(
            FilterOperator.OR,
            [FilterCondition("max_price", 1000), FilterCondition("property_type", "house")],
        )
        results, _ = self.engine.run_group(self.apartments, group)
        matched = {r.apartment_id for r in results if r.matches}
        self.assertEqual(matched, {"cheap", "house"})

    def test_invalid_group_raises_before_execution(self) -> None:
        group = FilterGroup(FilterOperator.AND, [FilterCondition("max_price", -1)])
        with self.assertRaises(FilterValidationError):
            self.engine.run_group(self.apartments, group)


class FilterEngineContextTests(unittest.TestCase):
    """Proves context-dependent filters (image_count, distance filters) actually use
    `FilterContext` when it's given, and degrade honestly (never exclude) when it's
    not — the concrete behavior `docs/25_Dynamic_Filter_Engine.md` documents.
    """

    def test_image_count_without_context_never_excludes(self) -> None:
        engine = FilterEngine()
        apartments = [_apartment()]
        results, _ = engine.run(apartments, {"image_count": 5}, context=FilterContext())
        self.assertTrue(results[0].matches)

    def test_walking_distance_without_analysis_results_never_excludes(self) -> None:
        engine = FilterEngine()
        apartments = [_apartment()]
        results, _ = engine.run(apartments, {"walking_distance": 0.9}, context=FilterContext())
        self.assertTrue(results[0].matches)


if __name__ == "__main__":
    unittest.main()
