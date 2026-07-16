"""`AvailabilityImportanceRule`/`PropertyTypePreferenceRule`/`MinimumAreaRule`/
`NumberOfRoomsRule`/`PlatformPreferenceRule` — five preference dimensions backed
by real `Apartment` fields (`current_status`/`property_type`/`sqft`/`bedrooms`/
`platform_id`). See docs/28_User_Feedback_and_Preference_Learning.md "Rules".
"""

from __future__ import annotations

from src.feedback.base_rule import (
    CategoricalPreferenceRule,
    ImportancePreferenceRule,
    PreferenceContext,
    ThresholdPreferenceRule,
)
from src.feedback.event_types import FeedbackEventType
from src.feedback.metadata import PreferenceRuleMetadata
from src.feedback.models import FeedbackEvent, PreferenceObservation
from src.feedback.registry import register_preference_rule

_POSITIVE_TYPES = frozenset(
    {FeedbackEventType.SAVED, FeedbackEventType.SHORTLISTED, FeedbackEventType.CONTACTED}
)
_NEGATIVE_TYPES = frozenset({FeedbackEventType.REJECTED, FeedbackEventType.IGNORED})


class AvailabilityImportanceRule(ImportancePreferenceRule):
    """Whether this user seems to care about current availability — a positive
    event on an unavailable listing suggests they don't filter on it much; a
    negative event on an unavailable listing (or a positive one on an available
    listing) suggests they do.
    """

    preference_key = "availability_importance"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES | _NEGATIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.apartment is None:
            return None
        is_available = context.apartment.current_status == "available"

        if event.event_type in _POSITIVE_TYPES:
            direction = "supporting" if is_available else "opposing"
        elif event.event_type in _NEGATIVE_TYPES:
            direction = "supporting" if not is_available else None
            if direction is None:
                return None
        else:
            return None

        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction=direction, magnitude=0.6, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} on a listing currently {context.apartment.current_status}",
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Availability Importance", category="logistics",
            description="Whether this user's save/reject decisions track current listing availability.",
            value_shape="importance", relevant_event_types=self.relevant_event_types(),
        )


class PropertyTypePreferenceRule(CategoricalPreferenceRule):
    preference_key = "property_type"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.apartment is None or not context.apartment.property_type:
            return None
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction="supporting", magnitude=1.0, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} a {context.apartment.property_type}",
            observed_value={"category": context.apartment.property_type},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Property Type", category="listing",
            description="Which property type this user positively engages with most.",
            value_shape="categorical", relevant_event_types=self.relevant_event_types(),
        )


class MinimumAreaRule(ThresholdPreferenceRule):
    preference_key = "minimum_area"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.apartment is None or context.apartment.sqft is None:
            return None
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction="supporting", magnitude=1.0, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} at {context.apartment.sqft:.0f} sqft",
            observed_value={"value": context.apartment.sqft},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Minimum Area", category="listing",
            description="A decayed-weighted average area (sqft) this user positively engages with.",
            value_shape="threshold", relevant_event_types=self.relevant_event_types(),
        )


class NumberOfRoomsRule(ThresholdPreferenceRule):
    preference_key = "number_of_rooms"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.apartment is None or context.apartment.bedrooms is None:
            return None
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction="supporting", magnitude=1.0, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} with {context.apartment.bedrooms} bedroom(s)",
            observed_value={"value": context.apartment.bedrooms},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Number of Rooms", category="listing",
            description="A decayed-weighted average bedroom count this user positively engages with.",
            value_shape="threshold", relevant_event_types=self.relevant_event_types(),
        )


class PlatformPreferenceRule(CategoricalPreferenceRule):
    preference_key = "platform"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.apartment is None:
            return None
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction="supporting", magnitude=1.0, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} a listing on {context.apartment.platform_id}",
            observed_value={"category": context.apartment.platform_id},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Platform Preference", category="listing",
            description="Which platform this user's positively-engaged listings come from most.",
            value_shape="categorical", relevant_event_types=self.relevant_event_types(),
        )


register_preference_rule(AvailabilityImportanceRule())
register_preference_rule(PropertyTypePreferenceRule())
register_preference_rule(MinimumAreaRule())
register_preference_rule(NumberOfRoomsRule())
register_preference_rule(PlatformPreferenceRule())
