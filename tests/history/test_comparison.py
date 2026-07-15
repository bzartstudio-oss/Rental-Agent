"""Unit tests for src/history/comparison.py — pure functions, no database, one test per
comparison method proving both the "changed" and "unchanged" (None/[]-returning) cases.
"""

import unittest
from datetime import datetime, timezone

from src.history import comparison
from src.history.models import ChangeType


class ComparePriceTests(unittest.TestCase):
    def test_returns_none_when_unchanged(self) -> None:
        self.assertIsNone(comparison.compare_price("apt-1", 1000.0, 1000.0, datetime.now(timezone.utc)))

    def test_returns_a_change_when_price_differs(self) -> None:
        change = comparison.compare_price("apt-1", 1000.0, 950.0, datetime.now(timezone.utc), search_id="s1")

        self.assertEqual(change.change_type, ChangeType.PRICE_CHANGED)
        self.assertEqual(change.field_name, "price")
        self.assertEqual(change.old_value, "1000.0")
        self.assertEqual(change.new_value, "950.0")
        self.assertEqual(change.search_id, "s1")


class CompareAvailabilityTests(unittest.TestCase):
    def test_returns_none_when_unchanged(self) -> None:
        self.assertIsNone(comparison.compare_availability("apt-1", "available", "available", datetime.now(timezone.utc)))

    def test_returns_a_change_when_status_differs(self) -> None:
        change = comparison.compare_availability("apt-1", "available", "rented", datetime.now(timezone.utc))

        self.assertEqual(change.change_type, ChangeType.AVAILABILITY_CHANGED)
        self.assertEqual(change.old_value, "available")
        self.assertEqual(change.new_value, "rented")


class CompareTitleTests(unittest.TestCase):
    def test_returns_none_when_unchanged(self) -> None:
        self.assertIsNone(comparison.compare_title("apt-1", "Sunny 2BR", "Sunny 2BR", datetime.now(timezone.utc)))

    def test_first_observation_has_null_old_value(self) -> None:
        change = comparison.compare_title("apt-1", None, "Sunny 2BR", datetime.now(timezone.utc))

        self.assertEqual(change.change_type, ChangeType.TITLE_CHANGED)
        self.assertIsNone(change.old_value)
        self.assertEqual(change.new_value, "Sunny 2BR")

    def test_returns_a_change_when_title_differs(self) -> None:
        change = comparison.compare_title("apt-1", "Sunny 2BR", "Renovated Sunny 2BR", datetime.now(timezone.utc))

        self.assertEqual(change.old_value, "Sunny 2BR")
        self.assertEqual(change.new_value, "Renovated Sunny 2BR")


class CompareDescriptionTests(unittest.TestCase):
    def test_returns_none_when_both_absent(self) -> None:
        self.assertIsNone(comparison.compare_description("apt-1", None, None, datetime.now(timezone.utc)))

    def test_returns_a_change_when_description_added(self) -> None:
        change = comparison.compare_description("apt-1", None, "Newly renovated.", datetime.now(timezone.utc))

        self.assertEqual(change.change_type, ChangeType.DESCRIPTION_CHANGED)
        self.assertIsNone(change.old_value)
        self.assertEqual(change.new_value, "Newly renovated.")


class CompareCoordinatesTests(unittest.TestCase):
    def test_returns_none_when_unchanged(self) -> None:
        self.assertIsNone(
            comparison.compare_coordinates("apt-1", 40.1, -3.7, 40.1, -3.7, datetime.now(timezone.utc))
        )

    def test_returns_a_change_when_coordinates_differ(self) -> None:
        change = comparison.compare_coordinates("apt-1", None, None, 40.1, -3.7, datetime.now(timezone.utc))

        self.assertEqual(change.change_type, ChangeType.COORDINATES_CHANGED)
        self.assertIsNone(change.old_value)
        self.assertEqual(change.new_value, "40.1,-3.7")


class CompareImagesTests(unittest.TestCase):
    def test_returns_empty_list_when_unchanged(self) -> None:
        self.assertEqual(comparison.compare_images("apt-1", ["a.jpg", "b.jpg"], ["a.jpg", "b.jpg"], datetime.now(timezone.utc)), [])

    def test_new_apartment_reports_every_image_as_added_in_order(self) -> None:
        changes = comparison.compare_images("apt-1", [], ["a.jpg", "b.jpg"], datetime.now(timezone.utc))

        self.assertEqual([c.change_type for c in changes], [ChangeType.IMAGE_ADDED, ChangeType.IMAGE_ADDED])
        self.assertEqual([c.new_value for c in changes], ["a.jpg", "b.jpg"])

    def test_detects_added_and_removed_images(self) -> None:
        changes = comparison.compare_images("apt-1", ["a.jpg", "b.jpg"], ["a.jpg", "c.jpg"], datetime.now(timezone.utc))

        added = [c for c in changes if c.change_type == ChangeType.IMAGE_ADDED]
        removed = [c for c in changes if c.change_type == ChangeType.IMAGE_REMOVED]
        self.assertEqual([c.new_value for c in added], ["c.jpg"])
        self.assertEqual([c.old_value for c in removed], ["b.jpg"])


class ComparePresenceTests(unittest.TestCase):
    def test_returns_none_when_presence_unchanged(self) -> None:
        self.assertIsNone(comparison.compare_presence("apt-1", True, True, datetime.now(timezone.utc)))
        self.assertIsNone(comparison.compare_presence("apt-1", False, False, datetime.now(timezone.utc)))

    def test_detects_listing_removed(self) -> None:
        change = comparison.compare_presence("apt-1", True, False, datetime.now(timezone.utc))
        self.assertEqual(change.change_type, ChangeType.LISTING_REMOVED)

    def test_detects_listing_returned(self) -> None:
        change = comparison.compare_presence("apt-1", False, True, datetime.now(timezone.utc))
        self.assertEqual(change.change_type, ChangeType.LISTING_RETURNED)


class SummarizeListingUpdatedTests(unittest.TestCase):
    def test_returns_none_for_no_changes(self) -> None:
        self.assertIsNone(comparison.summarize_listing_updated("apt-1", [], datetime.now(timezone.utc)))

    def test_summarizes_changed_field_names(self) -> None:
        now = datetime.now(timezone.utc)
        changes = [
            comparison.compare_price("apt-1", 1000.0, 950.0, now),
            comparison.compare_title("apt-1", "Old", "New", now),
        ]
        summary = comparison.summarize_listing_updated("apt-1", changes, now)

        self.assertEqual(summary.change_type, ChangeType.LISTING_UPDATED)
        self.assertIn("price", summary.new_value)
        self.assertIn("title", summary.new_value)


if __name__ == "__main__":
    unittest.main()
