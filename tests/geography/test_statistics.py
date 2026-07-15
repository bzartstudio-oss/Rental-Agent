"""Unit tests for GeoStatistics — src/geography/statistics.py."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.geography.models import GeoEnrichment, GeoResult, NearbyPlace, TravelMode
from src.geography.statistics import compute_geo_statistics

_NOW = datetime.now(timezone.utc)


def _result(mode: TravelMode, confidence: float) -> GeoResult:
    return GeoResult(
        origin=(0, 0), destination=(0, 1), mode=mode, distance_km=1.0, travel_time_minutes=10.0,
        confidence=confidence, computed_at=_NOW, provider_id="haversine", calculation_method="haversine",
    )


class GeoStatisticsTests(unittest.TestCase):
    def test_empty_enrichments_yield_honest_none_coverage(self) -> None:
        stats = compute_geo_statistics({})
        self.assertEqual(stats.total_apartments, 0)
        self.assertIsNone(stats.coverage_rate)

    def test_coverage_rate_counts_enriched_apartments(self) -> None:
        enriched = GeoEnrichment(
            apartment_id="a1", distances={TravelMode.STRAIGHT_LINE: _result(TravelMode.STRAIGHT_LINE, 1.0)},
        )
        empty = GeoEnrichment(apartment_id="a2")
        stats = compute_geo_statistics({"a1": enriched, "a2": empty})
        self.assertEqual(stats.total_apartments, 2)
        self.assertEqual(stats.enriched_count, 1)
        self.assertEqual(stats.coverage_rate, 0.5)

    def test_average_confidence_by_mode(self) -> None:
        e1 = GeoEnrichment(apartment_id="a1", distances={TravelMode.WALKING: _result(TravelMode.WALKING, 0.4)})
        e2 = GeoEnrichment(apartment_id="a2", distances={TravelMode.WALKING: _result(TravelMode.WALKING, 0.6)})
        stats = compute_geo_statistics({"a1": e1, "a2": e2})
        self.assertAlmostEqual(stats.average_confidence_by_mode["walking"], 0.5)

    def test_nearby_coverage_by_category_reflects_real_evidence_only(self) -> None:
        with_evidence = NearbyPlace(
            category="supermarket", count=3, distance_km=None, travel_time_minutes=None,
            confidence=0.8, computed_at=_NOW, provider_id="haversine", calculation_method="knowledge_entries",
        )
        without_evidence = NearbyPlace(
            category="supermarket", count=None, distance_km=None, travel_time_minutes=None,
            confidence=None, computed_at=_NOW, provider_id="haversine", calculation_method="knowledge_entries",
        )
        e1 = GeoEnrichment(apartment_id="a1", nearby={"supermarket": [with_evidence]})
        e2 = GeoEnrichment(apartment_id="a2", nearby={"supermarket": [without_evidence]})
        stats = compute_geo_statistics({"a1": e1, "a2": e2})
        self.assertEqual(stats.nearby_coverage_by_category["supermarket"], 0.5)

    def test_as_dict_is_json_safe(self) -> None:
        import json

        stats = compute_geo_statistics({})
        json.dumps(stats.as_dict())  # must not raise


if __name__ == "__main__":
    unittest.main()
