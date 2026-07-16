"""`WalkingDistanceImportanceRule`/`PublicTransportImportanceRule`/
`LifestyleImportanceRule`/`NearbyServicesImportanceRule`/`NeighborhoodPreferenceRule`
— the five geography-linked preference dimensions. See
docs/28_User_Feedback_and_Preference_Learning.md "Rules".

All read `context.geo_enrichment` — this run's own `GeoEnrichment` for the
apartment in question (Geographic Intelligence Engine, v2.5 Step 10) — never
recomputing a distance or nearby count themselves.
"""

from __future__ import annotations

from src.feedback.base_rule import CategoricalPreferenceRule, ImportancePreferenceRule, PreferenceContext
from src.feedback.event_types import FeedbackEventType
from src.feedback.metadata import PreferenceRuleMetadata
from src.feedback.models import FeedbackEvent, PreferenceObservation
from src.feedback.registry import register_preference_rule
from src.geography.models import TravelMode

_POSITIVE_TYPES = frozenset(
    {FeedbackEventType.SAVED, FeedbackEventType.SHORTLISTED, FeedbackEventType.CONTACTED}
)
_NEGATIVE_TYPES = frozenset({FeedbackEventType.REJECTED, FeedbackEventType.IGNORED})

# Documented, tunable thresholds — short/long framing mirrors ranking_v2's own
# walking/public-transport rules (src/ranking_v2/rules/geo_rules.py).
_SHORT_MINUTES = 15.0
_LONG_MINUTES = 30.0


class _TravelModeImportanceRule(ImportancePreferenceRule):
    """Shared observe() for the two travel-time importance rules — only
    `preference_key`/`_mode` differ.
    """

    _mode: TravelMode

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES | _NEGATIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.geo_enrichment is None:
            return None
        result = context.geo_enrichment.distances.get(self._mode)
        if result is None or result.travel_time_minutes is None:
            return None

        minutes = result.travel_time_minutes
        if event.event_type in _POSITIVE_TYPES:
            if minutes <= _SHORT_MINUTES:
                direction = "supporting"
            elif minutes >= _LONG_MINUTES:
                direction = "opposing"
            else:
                return None
        elif event.event_type in _NEGATIVE_TYPES:
            if minutes >= _LONG_MINUTES:
                direction = "supporting"
            else:
                return None
        else:
            return None

        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction=direction, magnitude=result.confidence, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} at {minutes:.0f} min", observed_value={"minutes": minutes},
        )


class WalkingDistanceImportanceRule(_TravelModeImportanceRule):
    preference_key = "walking_distance"
    _mode = TravelMode.WALKING

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Walking Distance Importance", category="location",
            description="How much walking time to the reference point drives this user's decisions.",
            value_shape="importance", relevant_event_types=self.relevant_event_types(),
        )


class PublicTransportImportanceRule(_TravelModeImportanceRule):
    preference_key = "public_transport"
    _mode = TravelMode.PUBLIC_TRANSPORT

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Public Transport Importance", category="location",
            description="How much public transport time to the reference point drives this user's decisions.",
            value_shape="importance", relevant_event_types=self.relevant_event_types(),
        )


class LifestyleImportanceRule(ImportancePreferenceRule):
    """Overall confirmed nearby-amenity coverage — reuses the exact scoring
    approach `ranking_v2.rules.geo_rules.LifestyleRankingRule` already uses
    (average of `min(count, 5) / 5` across confirmed categories), applied here to
    whether that coverage correlates with positive/negative feedback.
    """

    preference_key = "lifestyle"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES | _NEGATIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.geo_enrichment is None or not context.geo_enrichment.nearby:
            return None
        confirmed = [
            place.count for places in context.geo_enrichment.nearby.values() for place in places
            if place.count is not None
        ]
        if not confirmed:
            return None

        coverage = sum(min(count, 5) / 5 for count in confirmed) / len(confirmed)
        if event.event_type in _POSITIVE_TYPES:
            direction = "supporting" if coverage >= 0.5 else "opposing"
        elif event.event_type in _NEGATIVE_TYPES:
            direction = "supporting" if coverage < 0.3 else None
            if direction is None:
                return None
        else:
            return None

        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction=direction, magnitude=0.6, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} with lifestyle coverage {coverage:.2f}",
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Lifestyle Importance", category="location",
            description="Whether overall confirmed nearby-amenity coverage correlates with this user's decisions.",
            value_shape="importance", relevant_event_types=self.relevant_event_types(),
        )


class NearbyServicesImportanceRule(ImportancePreferenceRule):
    """Distinct from `lifestyle`: this tracks how many *distinct* confirmed
    categories a positively-engaged apartment has (breadth of nearby services),
    rather than lifestyle's per-category coverage average.
    """

    preference_key = "nearby_services"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.geo_enrichment is None or not context.geo_enrichment.nearby:
            return None
        confirmed_categories = [
            category for category, places in context.geo_enrichment.nearby.items()
            if any(place.count is not None for place in places)
        ]
        if not confirmed_categories:
            return None

        direction = "supporting" if len(confirmed_categories) >= 2 else "opposing"
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction=direction, magnitude=0.5, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} with {len(confirmed_categories)} confirmed nearby categories",
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Nearby Services Importance", category="location",
            description="Whether the breadth of confirmed nearby-service categories correlates with this user's decisions.",
            value_shape="importance", relevant_event_types=self.relevant_event_types(),
        )


class NeighborhoodPreferenceRule(CategoricalPreferenceRule):
    """The search `location` string is the only geography granularity this schema
    has (no structured neighborhood/region field exists — see
    `docs/03_Data_Model.md`) — an honest, coarse proxy for "neighborhood or
    geography preferences," not a fine-grained one.
    """

    preference_key = "neighborhood"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if not context.location:
            return None
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction="supporting", magnitude=1.0, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} a listing in {context.location}",
            observed_value={"category": context.location},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Neighborhood Preference", category="location",
            description="Which search location this user positively engages with most (coarse — no finer geography field exists).",
            value_shape="categorical", relevant_event_types=self.relevant_event_types(),
        )


register_preference_rule(WalkingDistanceImportanceRule())
register_preference_rule(PublicTransportImportanceRule())
register_preference_rule(LifestyleImportanceRule())
register_preference_rule(NearbyServicesImportanceRule())
register_preference_rule(NeighborhoodPreferenceRule())
