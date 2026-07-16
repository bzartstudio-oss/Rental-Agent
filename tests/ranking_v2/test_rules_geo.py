"""Unit tests for WalkingDistanceRankingRule/PublicTransportRankingRule/
LifestyleRankingRule — src/ranking_v2/rules/geo_rules.py.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.geography.models import GeoEnrichment, GeoResult, NearbyPlace, TravelMode
from src.ranking_v2.base_rule import RankingContext
from src.ranking_v2.rules.geo_rules import (
    LifestyleRankingRule,
    PublicTransportRankingRule,
    WalkingDistanceRankingRule,
)
from src.storage.models import Apartment

_NOW = datetime.now(timezone.utc)


def _apartment() -> Apartment:
    return Apartment(
        id="apt-1", platform_id="p1", platform_listing_id="l1", title="Test", url="u",
        current_price=1000, current_status="available", first_seen_at=_NOW, last_seen_at=_NOW,
    )


def _geo_result(mode: TravelMode, minutes: float, confidence: float = 0.4) -> GeoResult:
    return GeoResult(
        origin=(0, 0), destination=(0, 1), mode=mode, distance_km=1.0, travel_time_minutes=minutes,
        confidence=confidence, computed_at=_NOW, provider_id="haversine", calculation_method="haversine+estimated",
    )


class WalkingDistanceRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = WalkingDistanceRankingRule()

    def test_no_geo_enrichments_is_honest_no_evidence(self) -> None:
        evidence = self.rule.evaluate(_apartment(), RankingContext())
        self.assertIsNone(evidence.raw_score)

    def test_short_walk_scores_highly(self) -> None:
        enrichment = GeoEnrichment(apartment_id="apt-1", distances={TravelMode.WALKING: _geo_result(TravelMode.WALKING, 5)})
        context = RankingContext(geo_enrichments={"apt-1": enrichment})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertGreater(evidence.raw_score, 0.85)
        self.assertEqual(evidence.confidence, 0.4)  # reuses the GeoResult's own honest confidence

    def test_long_walk_scores_poorly(self) -> None:
        enrichment = GeoEnrichment(apartment_id="apt-1", distances={TravelMode.WALKING: _geo_result(TravelMode.WALKING, 60)})
        context = RankingContext(geo_enrichments={"apt-1": enrichment})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertEqual(evidence.raw_score, 0.0)


class PublicTransportRankingRuleTests(unittest.TestCase):
    def test_reads_the_public_transport_mode_specifically(self) -> None:
        rule = PublicTransportRankingRule()
        enrichment = GeoEnrichment(
            apartment_id="apt-1",
            distances={
                TravelMode.WALKING: _geo_result(TravelMode.WALKING, 60),
                TravelMode.PUBLIC_TRANSPORT: _geo_result(TravelMode.PUBLIC_TRANSPORT, 8),
            },
        )
        context = RankingContext(geo_enrichments={"apt-1": enrichment})
        evidence = rule.evaluate(_apartment(), context)
        self.assertGreater(evidence.raw_score, 0.8)


class LifestyleRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = LifestyleRankingRule()

    def test_no_nearby_data_is_honest_no_evidence(self) -> None:
        enrichment = GeoEnrichment(apartment_id="apt-1")
        context = RankingContext(geo_enrichments={"apt-1": enrichment})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertIsNone(evidence.raw_score)

    def test_uncurated_categories_are_excluded_not_penalized(self) -> None:
        no_evidence_place = NearbyPlace(
            category="hospital", count=None, distance_km=None, travel_time_minutes=None,
            confidence=None, computed_at=_NOW, provider_id="haversine", calculation_method="knowledge_entries",
            warnings=["No curated 'hospital' data yet"],
        )
        enrichment = GeoEnrichment(apartment_id="apt-1", nearby={"hospital": [no_evidence_place]})
        context = RankingContext(geo_enrichments={"apt-1": enrichment})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertIsNone(evidence.raw_score)

    def test_confirmed_amenities_score_positively(self) -> None:
        confirmed_place = NearbyPlace(
            category="supermarket", count=5, distance_km=None, travel_time_minutes=None,
            confidence=0.8, computed_at=_NOW, provider_id="haversine", calculation_method="knowledge_entries",
        )
        enrichment = GeoEnrichment(apartment_id="apt-1", nearby={"supermarket": [confirmed_place]})
        context = RankingContext(geo_enrichments={"apt-1": enrichment})
        evidence = self.rule.evaluate(_apartment(), context)
        self.assertEqual(evidence.raw_score, 1.0)
        self.assertEqual(evidence.confidence, 0.8)
        self.assertIn("supermarket", evidence.detail)


if __name__ == "__main__":
    unittest.main()
