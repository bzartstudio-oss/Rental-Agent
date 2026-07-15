"""Unit tests for the 12 data-backed built-in filters — src/filter_engine/filters/
core_filters.py + distance_filters.py.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.models import AnalysisResult, AnalyzerResult
from src.discovery import platform_registry
from src.filter_engine.base_filter import FilterContext
from src.filter_engine.factory import FilterFactory
from src.storage import apartment_repository
from src.storage.database import Database
from src.storage.models import Apartment, ApartmentImage, Platform


def _apartment(**overrides) -> Apartment:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="a1", platform_id="p1", platform_listing_id="1", title="A Place", url="x",
        current_price=1000.0, current_status="available", first_seen_at=now, last_seen_at=now,
    )
    defaults.update(overrides)
    return Apartment(**defaults)


class PriceAndAreaFilterTests(unittest.TestCase):
    def test_max_price_delegates_to_legacy_criteria(self) -> None:
        f = FilterFactory.get("max_price")
        self.assertTrue(f.apply(_apartment(current_price=1000), 2000, FilterContext()))
        self.assertFalse(f.apply(_apartment(current_price=3000), 2000, FilterContext()))

    def test_min_price_delegates_to_legacy_criteria(self) -> None:
        f = FilterFactory.get("min_price")
        self.assertTrue(f.apply(_apartment(current_price=1000), 500, FilterContext()))
        self.assertFalse(f.apply(_apartment(current_price=300), 500, FilterContext()))

    def test_minimum_area_delegates_to_legacy_min_sqft(self) -> None:
        f = FilterFactory.get("minimum_area")
        self.assertTrue(f.apply(_apartment(sqft=800), 500, FilterContext()))
        self.assertFalse(f.apply(_apartment(sqft=300), 500, FilterContext()))

    def test_maximum_area_excludes_larger_apartments(self) -> None:
        f = FilterFactory.get("maximum_area")
        self.assertTrue(f.apply(_apartment(sqft=300), 500, FilterContext()))
        self.assertFalse(f.apply(_apartment(sqft=800), 500, FilterContext()))

    def test_maximum_area_excludes_unknown_area(self) -> None:
        f = FilterFactory.get("maximum_area")
        self.assertFalse(f.apply(_apartment(sqft=None), 500, FilterContext()))


class NumberOfRoomsFilterTests(unittest.TestCase):
    def test_exact_match_required(self) -> None:
        f = FilterFactory.get("number_of_rooms")
        self.assertTrue(f.apply(_apartment(bedrooms=2), 2, FilterContext()))
        self.assertFalse(f.apply(_apartment(bedrooms=3), 2, FilterContext()))

    def test_unknown_bedrooms_never_matches(self) -> None:
        f = FilterFactory.get("number_of_rooms")
        self.assertFalse(f.apply(_apartment(bedrooms=None), 2, FilterContext()))


class CurrencyAndPropertyTypeFilterTests(unittest.TestCase):
    def test_currency_matches_case_insensitively(self) -> None:
        f = FilterFactory.get("currency")
        self.assertTrue(f.apply(_apartment(currency="usd"), "USD", FilterContext()))

    def test_currency_unknown_never_matches(self) -> None:
        f = FilterFactory.get("currency")
        self.assertFalse(f.apply(_apartment(currency=None), "USD", FilterContext()))

    def test_property_type_matches_case_insensitively(self) -> None:
        f = FilterFactory.get("property_type")
        self.assertTrue(f.apply(_apartment(property_type="Apartment"), "apartment", FilterContext()))


class PlatformFilterTests(unittest.TestCase):
    def test_single_platform_value(self) -> None:
        f = FilterFactory.get("platform")
        self.assertTrue(f.apply(_apartment(platform_id="rentcast"), "rentcast", FilterContext()))
        self.assertFalse(f.apply(_apartment(platform_id="demo_platform"), "rentcast", FilterContext()))

    def test_list_of_platforms(self) -> None:
        f = FilterFactory.get("platform")
        self.assertTrue(f.apply(_apartment(platform_id="demo_platform"), ["rentcast", "demo_platform"], FilterContext()))


class ImageCountFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_without_conn_never_excludes(self) -> None:
        f = FilterFactory.get("image_count")
        self.assertTrue(f.apply(_apartment(), 5, FilterContext()))

    def test_with_conn_counts_real_current_images(self) -> None:
        now = datetime.now(timezone.utc)
        f = FilterFactory.get("image_count")
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(id="p1", name="P1", country="N/A", homepage="x", connector_available=True, created_at=now),
            )
            apartment_repository.insert_apartment(conn, _apartment())
            apartment_repository.add_image(
                conn, ApartmentImage(apartment_id="a1", source_url="x", local_path="x", downloaded_at=now)
            )
            context = FilterContext(conn=conn)
            self.assertTrue(f.apply(_apartment(), 1, context))
            self.assertFalse(f.apply(_apartment(), 2, context))


class DistanceFilterTests(unittest.TestCase):
    def _analysis_results(self, score: float | None) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "a1": AnalysisResult(
                apartment_id="a1", search_id="s1", computed_at=now,
                analyzer_results=[
                    AnalyzerResult(
                        analyzer_name="walking_distance", apartment_id="a1", score=score,
                        confidence=1.0 if score is not None else None, evidence=[], warnings=[],
                        computed_at=now, version="1.0.0", source="haversine_calculation",
                    )
                ],
                composite_scores=[],
            )
        }

    def test_walking_distance_matches_when_score_meets_threshold(self) -> None:
        f = FilterFactory.get("walking_distance")
        context = FilterContext(analysis_results=self._analysis_results(0.8))
        self.assertTrue(f.apply(_apartment(), 0.5, context))

    def test_walking_distance_excludes_below_threshold(self) -> None:
        f = FilterFactory.get("walking_distance")
        context = FilterContext(analysis_results=self._analysis_results(0.2))
        self.assertFalse(f.apply(_apartment(), 0.5, context))

    def test_walking_distance_no_evidence_never_excludes(self) -> None:
        f = FilterFactory.get("walking_distance")
        context = FilterContext(analysis_results=self._analysis_results(None))
        self.assertTrue(f.apply(_apartment(), 0.9, context))

    def test_validate_rejects_out_of_range_score(self) -> None:
        f = FilterFactory.get("walking_distance")
        with self.assertRaises(ValueError):
            f.validate(1.5)


if __name__ == "__main__":
    unittest.main()
