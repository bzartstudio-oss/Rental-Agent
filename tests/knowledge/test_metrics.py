"""Unit tests for src/knowledge/metrics.py — pure functions, no database."""

import unittest

from src.connectors.base import RawListing
from src.knowledge import metrics
from src.ranking.ranking_engine import RankedApartment
from src.storage.models import Apartment


def _raw(listing_id="l1", title="Title", price=1000.0, url="https://example.com/1",
         bedrooms=2.0, bathrooms=1.0, sqft=800.0, address_raw="123 Main St",
         status="available", image_urls=None) -> RawListing:
    return RawListing(
        platform_listing_id=listing_id, title=title, price=price, url=url,
        bedrooms=bedrooms, bathrooms=bathrooms, sqft=sqft, address_raw=address_raw,
        status=status, image_urls=image_urls or [],
    )


class ExtractionQualityScoreTests(unittest.TestCase):
    def test_returns_none_for_no_listings(self) -> None:
        self.assertIsNone(metrics.extraction_quality_score([]))

    def test_complete_listing_scores_one(self) -> None:
        self.assertEqual(metrics.extraction_quality_score([_raw()]), 1.0)

    def test_missing_fields_lower_the_score(self) -> None:
        incomplete = _raw(bedrooms=None, bathrooms=None, address_raw=None)
        score = metrics.extraction_quality_score([incomplete])
        self.assertAlmostEqual(score, 4 / 7)

    def test_blank_string_field_counts_as_missing(self) -> None:
        incomplete = _raw(address_raw="   ")
        score = metrics.extraction_quality_score([incomplete])
        self.assertAlmostEqual(score, 6 / 7)


class ImageQualityScoreTests(unittest.TestCase):
    def test_returns_none_for_no_listings(self) -> None:
        self.assertIsNone(metrics.image_quality_score([]))

    def test_fraction_with_at_least_one_image(self) -> None:
        listings = [_raw(image_urls=["a.jpg"]), _raw(image_urls=[])]
        self.assertEqual(metrics.image_quality_score(listings), 0.5)


class AvailabilityQualityScoreTests(unittest.TestCase):
    def test_returns_none_for_no_listings(self) -> None:
        self.assertIsNone(metrics.availability_quality_score([]))

    def test_fraction_with_a_reported_status(self) -> None:
        listings = [_raw(status="available"), _raw(status=None)]
        self.assertEqual(metrics.availability_quality_score(listings), 0.5)

    def test_all_missing_status_scores_zero(self) -> None:
        listings = [_raw(status=None), _raw(status=None)]
        self.assertEqual(metrics.availability_quality_score(listings), 0.0)


class DuplicateRateTests(unittest.TestCase):
    def test_returns_none_for_no_listings(self) -> None:
        self.assertIsNone(metrics.duplicate_rate([]))

    def test_no_duplicates_scores_zero(self) -> None:
        listings = [_raw("a"), _raw("b")]
        self.assertEqual(metrics.duplicate_rate(listings), 0.0)

    def test_detects_duplicate_listing_ids(self) -> None:
        listings = [_raw("a"), _raw("a"), _raw("b")]
        self.assertAlmostEqual(metrics.duplicate_rate(listings), 1 / 3)


class RankingUsefulnessScoreTests(unittest.TestCase):
    def _apartment(self, apartment_id: str, platform_id: str) -> Apartment:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return Apartment(
            id=apartment_id, platform_id=platform_id, platform_listing_id=apartment_id,
            title="x", url="https://example.com/x", current_price=1000.0,
            current_status="available", first_seen_at=now, last_seen_at=now,
        )

    def _ranked(self, apartment: Apartment, rank: int) -> RankedApartment:
        return RankedApartment(apartment=apartment, rank=rank, score=1.0, score_breakdown={})

    def test_returns_none_with_no_candidates(self) -> None:
        self.assertIsNone(metrics.ranking_usefulness_score("p1", [], []))

    def test_returns_none_when_platform_contributed_nothing(self) -> None:
        apartments = [self._apartment("a1", "p2")]
        self.assertIsNone(metrics.ranking_usefulness_score("p1", [], apartments))

    def test_platform_punching_above_its_weight_scores_above_one(self) -> None:
        # p1 has 1 of 4 candidates but takes 1 of 2 top-N slots -> 0.5 / 0.25 = 2.0
        apartments = [self._apartment(f"a{i}", "p1" if i == 0 else "p2") for i in range(4)]
        ranked = [self._ranked(apartments[0], 1), self._ranked(apartments[1], 2)]
        score = metrics.ranking_usefulness_score("p1", ranked, apartments, top_n=2)
        self.assertEqual(score, 2.0)

    def test_platform_matching_its_weight_scores_one(self) -> None:
        apartments = [self._apartment(f"a{i}", "p1") for i in range(2)] + [
            self._apartment(f"b{i}", "p2") for i in range(2)
        ]
        ranked = [self._ranked(apartments[0], 1), self._ranked(apartments[2], 2)]
        score = metrics.ranking_usefulness_score("p1", ranked, apartments, top_n=2)
        self.assertEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
