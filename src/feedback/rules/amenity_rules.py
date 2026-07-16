"""Group-B preference dimensions: private bathroom, private kitchen, air
conditioning, furnished status, pets, balcony, parking, utilities included,
internet included, preferred room types, number of flatmates.

None of these have a structured `Apartment`/`RawListing` field anywhere in this
schema — the same 27-of-39 "dormant filter" situation `filter_engine`'s own
`amenities.py`/`preferences_and_other.py` already documented for the identical
fields (v2.5 Step 9). A SAVED/REJECTED apartment can never be checked for
"does it actually have a balcony," so these rules honestly learn only from
**explicit filter selections/removals** — real, structured evidence of intent,
even though it can never be corroborated against a listing outcome. Each
`preference_key` matches the identical `key` string
`filter_engine.filters.amenities`/`preferences_and_other` already uses for the
same concept, so a user's filter choice and the learned preference are one idea,
not two competing ones. See docs/28_User_Feedback_and_Preference_Learning.md
"Rules" and "Filter Engine Integration."
"""

from __future__ import annotations

from src.feedback.base_rule import (
    BooleanPreferenceRule,
    CategoricalPreferenceRule,
    PreferenceContext,
    ThresholdPreferenceRule,
)
from src.feedback.event_types import FeedbackEventType
from src.feedback.metadata import PreferenceRuleMetadata
from src.feedback.models import FeedbackEvent, PreferenceObservation
from src.feedback.registry import register_preference_rule

_RELEVANT_TYPES = frozenset({FeedbackEventType.FILTER_SELECTED, FeedbackEventType.FILTER_REMOVED})


class _FilterChoiceBooleanPreferenceRule(BooleanPreferenceRule):
    """Shared `observe()` for every boolean amenity preference below — a
    `FILTER_SELECTED` event with `value=True` supports wanting it, `value=False`
    opposes; a `FILTER_REMOVED` event weakly opposes (the user stopped requiring
    it, not necessarily that they dislike it — hence the lower magnitude).
    """

    _display_name: str

    def relevant_event_types(self) -> frozenset[str]:
        return _RELEVANT_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if event.event_value.get("key") != self.preference_key:
            return None

        if event.event_type == FeedbackEventType.FILTER_SELECTED:
            value = bool(event.event_value.get("value"))
            direction = "supporting" if value else "opposing"
            magnitude = 1.0
        else:  # FILTER_REMOVED
            direction = "opposing"
            magnitude = 0.4

        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction=direction, magnitude=magnitude, source_type="explicit", computed_at=event.occurred_at,
            explanation=f"{event.event_type}: {self.preference_key}={event.event_value.get('value')}",
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name=self._display_name, category="amenity",
            description=(
                f"Whether the user wants {self._display_name.lower()}, learned only from explicit filter "
                "choices — no listing field exists to verify against a saved/rejected outcome."
            ),
            value_shape="boolean", learns_from_listing_fields=False, relevant_event_types=self.relevant_event_types(),
        )


class PrivateBathroomPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "private_bathroom"
    _display_name = "Private Bathroom"


class PrivateKitchenPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "private_kitchen"
    _display_name = "Private Kitchen"


class AirConditioningPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "air_conditioning"
    _display_name = "Air Conditioning"


class FurnishedPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "furnished"
    _display_name = "Furnished"


class PetsPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "pets_allowed"
    _display_name = "Pets Allowed"


class BalconyPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "balcony"
    _display_name = "Balcony"


class ParkingPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "parking"
    _display_name = "Parking"


class UtilitiesIncludedPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "utilities_included"
    _display_name = "Utilities Included"


class InternetIncludedPreferenceRule(_FilterChoiceBooleanPreferenceRule):
    preference_key = "internet_included"
    _display_name = "Internet Included"


class RoomTypePreferenceRule(CategoricalPreferenceRule):
    """Learned only from explicit `FILTER_SELECTED` choices — `room_type` has no
    structured `Apartment` field either (same dormant-field situation).
    """

    preference_key = "room_type"

    def relevant_event_types(self) -> frozenset[str]:
        return frozenset({FeedbackEventType.FILTER_SELECTED})

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if event.event_value.get("key") != self.preference_key:
            return None
        value = event.event_value.get("value")
        if not value:
            return None
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction="supporting", magnitude=1.0, source_type="explicit", computed_at=event.occurred_at,
            explanation=f"filter selected: room_type={value}", observed_value={"category": value},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Room Type", category="amenity",
            description="Preferred room type, learned only from explicit filter choices (no listing field exists).",
            value_shape="categorical", learns_from_listing_fields=False,
            relevant_event_types=self.relevant_event_types(),
        )


class NumberOfFlatmatesPreferenceRule(ThresholdPreferenceRule):
    """Learned only from explicit `FILTER_SELECTED` choices — `number_of_flatmates`
    has no structured `Apartment` field either (same dormant-field situation).
    """

    preference_key = "number_of_flatmates"

    def relevant_event_types(self) -> frozenset[str]:
        return frozenset({FeedbackEventType.FILTER_SELECTED})

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if event.event_value.get("key") != self.preference_key:
            return None
        value = event.event_value.get("value")
        if value is None:
            return None
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction="supporting", magnitude=1.0, source_type="explicit", computed_at=event.occurred_at,
            explanation=f"filter selected: number_of_flatmates={value}", observed_value={"value": float(value)},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Number of Flatmates", category="amenity",
            description="Preferred flatmate count, learned only from explicit filter choices (no listing field exists).",
            value_shape="threshold", learns_from_listing_fields=False,
            relevant_event_types=self.relevant_event_types(),
        )


register_preference_rule(PrivateBathroomPreferenceRule())
register_preference_rule(PrivateKitchenPreferenceRule())
register_preference_rule(AirConditioningPreferenceRule())
register_preference_rule(FurnishedPreferenceRule())
register_preference_rule(PetsPreferenceRule())
register_preference_rule(BalconyPreferenceRule())
register_preference_rule(ParkingPreferenceRule())
register_preference_rule(UtilitiesIncludedPreferenceRule())
register_preference_rule(InternetIncludedPreferenceRule())
register_preference_rule(RoomTypePreferenceRule())
register_preference_rule(NumberOfFlatmatesPreferenceRule())
