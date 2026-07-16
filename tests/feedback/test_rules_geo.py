"""Unit tests for WalkingDistanceImportanceRule/PublicTransportImportanceRule/
LifestyleImportanceRule/NearbyServicesImportanceRule/NeighborhoodPreferenceRule —
src/feedback/rules/geo_rules.py.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.feedback.base_rule import PreferenceContext
from src.feedback.event_types import FeedbackEventType
from src.feedback.models import FeedbackEvent
from src.feedback.rules.geo_rules import (
    LifestyleImportanceRule,
    NearbyServicesImportanceRule,
    NeighborhoodPreferenceRule,
    PublicTransportImportanceRule,
    WalkingDistanceImportanceRule,
)
from src.geography.models import GeoEnrichment, GeoResult, NearbyPlace, TravelMode

_NOW = datetime.now(timezone.utc)


def _geo_result(mode: TravelMode, minutes: float) -> GeoResult:
    return GeoResult(origin=(0, 0), destination=(0, 1), mode=mode, distance_km=1.0, travel_time_minutes=minutes,
                      confidence=0.4, computed_at=_NOW, provider_id="haversine", calculation_method="est")


class WalkingDistanceImportanceRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = WalkingDistanceImportanceRule()

    def test_no_geo_enrichment_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        self.assertIsNone(self.rule.observe(event, PreferenceContext()))

    def test_saved_short_walk_supports_importance(self) -> None:
        enrichment = GeoEnrichment(apartment_id="apt-1", distances={TravelMode.WALKING: _geo_result(TravelMode.WALKING, 8)})
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = self.rule.observe(event, PreferenceContext(geo_enrichment=enrichment))
        self.assertEqual(observation.direction, "supporting")

    def test_rejected_long_walk_supports_importance(self) -> None:
        enrichment = GeoEnrichment(apartment_id="apt-1", distances={TravelMode.WALKING: _geo_result(TravelMode.WALKING, 45)})
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.REJECTED, occurred_at=_NOW, source="cli")
        observation = self.rule.observe(event, PreferenceContext(geo_enrichment=enrichment))
        self.assertEqual(observation.direction, "supporting")


class PublicTransportImportanceRuleTests(unittest.TestCase):
    def test_reads_public_transport_mode_specifically(self) -> None:
        enrichment = GeoEnrichment(
            apartment_id="apt-1",
            distances={TravelMode.PUBLIC_TRANSPORT: _geo_result(TravelMode.PUBLIC_TRANSPORT, 5)},
        )
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = PublicTransportImportanceRule().observe(event, PreferenceContext(geo_enrichment=enrichment))
        self.assertEqual(observation.direction, "supporting")


class LifestyleImportanceRuleTests(unittest.TestCase):
    def test_no_nearby_data_is_honest_no_evidence(self) -> None:
        enrichment = GeoEnrichment(apartment_id="apt-1")
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        self.assertIsNone(LifestyleImportanceRule().observe(event, PreferenceContext(geo_enrichment=enrichment)))

    def test_high_coverage_plus_saved_is_supporting(self) -> None:
        place = NearbyPlace(category="supermarket", count=5, distance_km=None, travel_time_minutes=None,
                             confidence=0.8, computed_at=_NOW, provider_id="haversine", calculation_method="x")
        enrichment = GeoEnrichment(apartment_id="apt-1", nearby={"supermarket": [place]})
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = LifestyleImportanceRule().observe(event, PreferenceContext(geo_enrichment=enrichment))
        self.assertEqual(observation.direction, "supporting")


class NearbyServicesImportanceRuleTests(unittest.TestCase):
    def test_multiple_confirmed_categories_is_supporting(self) -> None:
        place1 = NearbyPlace(category="supermarket", count=3, distance_km=None, travel_time_minutes=None,
                              confidence=0.8, computed_at=_NOW, provider_id="haversine", calculation_method="x")
        place2 = NearbyPlace(category="gym", count=2, distance_km=None, travel_time_minutes=None,
                              confidence=0.8, computed_at=_NOW, provider_id="haversine", calculation_method="x")
        enrichment = GeoEnrichment(apartment_id="apt-1", nearby={"supermarket": [place1], "gym": [place2]})
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = NearbyServicesImportanceRule().observe(event, PreferenceContext(geo_enrichment=enrichment))
        self.assertEqual(observation.direction, "supporting")


class NeighborhoodPreferenceRuleTests(unittest.TestCase):
    def test_no_location_is_honest_no_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        self.assertIsNone(NeighborhoodPreferenceRule().observe(event, PreferenceContext()))

    def test_location_produces_categorical_evidence(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli")
        observation = NeighborhoodPreferenceRule().observe(event, PreferenceContext(location="Downtown"))
        self.assertEqual(observation.observed_value, {"category": "Downtown"})


if __name__ == "__main__":
    unittest.main()
