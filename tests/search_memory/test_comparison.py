"""Unit tests for src/search_memory/comparison.py — pure functions, no database."""

import unittest

from src.search_memory import comparison


class DiffApartmentSetsTests(unittest.TestCase):
    def test_returns_empty_lists_when_sets_are_identical(self) -> None:
        new_ids, removed_ids = comparison.diff_apartment_sets({"a", "b"}, {"a", "b"})
        self.assertEqual(new_ids, [])
        self.assertEqual(removed_ids, [])

    def test_detects_new_and_removed_ids(self) -> None:
        new_ids, removed_ids = comparison.diff_apartment_sets({"a", "b"}, {"b", "c"})
        self.assertEqual(new_ids, ["c"])
        self.assertEqual(removed_ids, ["a"])

    def test_first_ever_search_has_no_previous_set(self) -> None:
        new_ids, removed_ids = comparison.diff_apartment_sets(set(), {"a", "b"})
        self.assertEqual(new_ids, ["a", "b"])
        self.assertEqual(removed_ids, [])


class PlatformCoverageChangeTests(unittest.TestCase):
    def test_no_change_when_searched_sets_are_identical(self) -> None:
        change = comparison.platform_coverage_change(["p1", "p2"], ["p1", "p2"])
        self.assertEqual(change.newly_searched_platform_ids, [])
        self.assertEqual(change.no_longer_searched_platform_ids, [])

    def test_detects_newly_and_no_longer_searched_platforms(self) -> None:
        change = comparison.platform_coverage_change(["p1", "p2"], ["p2", "p3"])
        self.assertEqual(change.newly_searched_platform_ids, ["p3"])
        self.assertEqual(change.no_longer_searched_platform_ids, ["p1"])


class SearchQualityTests(unittest.TestCase):
    def test_returns_none_when_no_platform_was_searched(self) -> None:
        self.assertIsNone(comparison.search_quality(10, 0))

    def test_returns_none_when_apartment_count_is_none(self) -> None:
        self.assertIsNone(comparison.search_quality(None, 2))

    def test_computes_apartments_per_searched_platform(self) -> None:
        self.assertEqual(comparison.search_quality(10, 2), 5.0)


if __name__ == "__main__":
    unittest.main()
