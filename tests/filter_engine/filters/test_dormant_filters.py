"""Unit tests for the 27 dormant built-in filters — src/filter_engine/filters/
amenities.py + preferences_and_other.py. Covers every filter's registration and
metadata (a real regression if any one of the 27 gets dropped or mis-keyed), plus
representative behavior tests per shared base class rather than repeating the same
assertion 27 times.
"""

from __future__ import annotations

from datetime import datetime, timezone

import unittest

from src.filter_engine.base_filter import FilterContext
from src.filter_engine.factory import FilterFactory
from src.filter_engine.registry import FilterRegistry
from src.storage.models import Apartment

_DORMANT_KEYS = [
    "private_bathroom", "private_kitchen", "air_conditioning", "heating", "balcony",
    "terrace", "parking", "elevator", "wheelchair_accessible", "pets_allowed",
    "smoking_allowed", "internet_included", "utilities_included", "furnished",
    "gender_preference", "student_friendly", "professional_friendly",
    "country", "region", "city", "radius",
    "availability_date", "minimum_stay", "maximum_stay",
    "room_type", "number_of_flatmates", "language",
]


def _apartment() -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id="a1", platform_id="p1", platform_listing_id="1", title="x", url="x",
        current_price=1000.0, current_status="available", first_seen_at=now, last_seen_at=now,
    )


class DormantFilterInventoryTests(unittest.TestCase):
    def test_every_expected_dormant_key_is_registered(self) -> None:
        self.assertEqual(len(_DORMANT_KEYS), 27)
        for key in _DORMANT_KEYS:
            self.assertTrue(FilterRegistry.is_registered(key), f"{key!r} should be registered")

    def test_every_dormant_filter_declares_is_dormant_true(self) -> None:
        for key in _DORMANT_KEYS:
            metadata = FilterFactory.get(key).metadata()
            self.assertTrue(metadata.is_dormant, f"{key!r} should be marked dormant")
            self.assertTrue(metadata.description)  # never an empty description


class DormantFilterBehaviorTests(unittest.TestCase):
    def test_boolean_dormant_filter_always_passes_regardless_of_value(self) -> None:
        f = FilterFactory.get("private_bathroom")
        self.assertTrue(f.apply(_apartment(), True, FilterContext()))
        self.assertTrue(f.apply(_apartment(), False, FilterContext()))

    def test_boolean_dormant_filter_rejects_non_boolean_value(self) -> None:
        f = FilterFactory.get("pets_allowed")
        with self.assertRaises(ValueError):
            f.validate("yes")

    def test_string_dormant_filter_always_passes(self) -> None:
        f = FilterFactory.get("city")
        self.assertTrue(f.apply(_apartment(), "Austin", FilterContext()))

    def test_string_dormant_filter_rejects_empty_value(self) -> None:
        f = FilterFactory.get("room_type")
        with self.assertRaises(ValueError):
            f.validate("")

    def test_number_dormant_filter_always_passes(self) -> None:
        f = FilterFactory.get("number_of_flatmates")
        self.assertTrue(f.apply(_apartment(), 3, FilterContext()))

    def test_number_dormant_filter_rejects_negative_value(self) -> None:
        f = FilterFactory.get("radius")
        with self.assertRaises(ValueError):
            f.validate(-5)

    def test_date_dormant_filter_always_passes(self) -> None:
        f = FilterFactory.get("availability_date")
        self.assertTrue(f.apply(_apartment(), "2026-08-01", FilterContext()))

    def test_date_dormant_filter_rejects_malformed_date(self) -> None:
        f = FilterFactory.get("availability_date")
        with self.assertRaises(ValueError):
            f.validate("not-a-date")

    def test_room_type_filter_reflects_the_sdk_validation_sprint_finding(self) -> None:
        """docs/22's Finding 1 — room_type has no backing field anywhere; this filter
        exists so the gap is queryable/discoverable, not silently absent.
        """
        f = FilterFactory.get("room_type")
        self.assertIn("Dormant", f.description())


if __name__ == "__main__":
    unittest.main()
