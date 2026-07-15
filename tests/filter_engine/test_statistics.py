"""Unit tests for compute_filter_statistics — src/filter_engine/statistics.py."""

from __future__ import annotations

import unittest

from src.filter_engine.result import FilterResult
from src.filter_engine.statistics import compute_filter_statistics


class ComputeFilterStatisticsTests(unittest.TestCase):
    def test_empty_results_produce_none_match_rate_not_a_crash(self) -> None:
        stats = compute_filter_statistics([])
        self.assertEqual(stats.total_apartments, 0)
        self.assertIsNone(stats.match_rate)
        self.assertEqual(stats.per_filter_pass_rate, {})

    def test_match_counts_and_rate(self) -> None:
        results = [
            FilterResult(apartment_id="a1", matches=True, per_filter={"max_price": True}),
            FilterResult(apartment_id="a2", matches=False, per_filter={"max_price": False}),
            FilterResult(apartment_id="a3", matches=True, per_filter={"max_price": True}),
        ]

        stats = compute_filter_statistics(results)

        self.assertEqual(stats.total_apartments, 3)
        self.assertEqual(stats.matched_count, 2)
        self.assertEqual(stats.excluded_count, 1)
        self.assertAlmostEqual(stats.match_rate, 2 / 3)

    def test_per_filter_pass_rate_is_independent_of_composed_match(self) -> None:
        """A filter can individually pass often while the composed AND still excludes
        most apartments, if ANDed with a stricter one — per_filter_pass_rate must
        reflect the individual filter, not the composed outcome.
        """
        results = [
            FilterResult(apartment_id="a1", matches=False, per_filter={"lenient": True, "strict": False}),
            FilterResult(apartment_id="a2", matches=False, per_filter={"lenient": True, "strict": False}),
            FilterResult(apartment_id="a3", matches=True, per_filter={"lenient": True, "strict": True}),
        ]

        stats = compute_filter_statistics(results)

        self.assertEqual(stats.per_filter_pass_rate["lenient"], 1.0)
        self.assertAlmostEqual(stats.per_filter_pass_rate["strict"], 1 / 3)

    def test_execution_time_is_carried_through(self) -> None:
        stats = compute_filter_statistics([], execution_time_ms=42)
        self.assertEqual(stats.execution_time_ms, 42)

    def test_as_dict_is_json_safe(self) -> None:
        stats = compute_filter_statistics(
            [FilterResult(apartment_id="a1", matches=True, per_filter={"max_price": True})], execution_time_ms=10
        )
        as_dict = stats.as_dict()
        self.assertEqual(as_dict["total_apartments"], 1)
        self.assertEqual(as_dict["per_filter_pass_rate"], {"max_price": 1.0})


if __name__ == "__main__":
    unittest.main()
