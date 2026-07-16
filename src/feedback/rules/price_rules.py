"""`PriceSensitivityRule`/`MaximumBudgetRule` — "price sensitivity" and "maximum
budget preference" from the mission's PREFERENCE MODEL list. See
docs/28_User_Feedback_and_Preference_Learning.md "Rules".

Both reuse the Knowledge Engine's own `average_city_price()` (v2.0 Step 4) as the
price baseline — neither recomputes a city average itself.
"""

from __future__ import annotations

from src.feedback.base_rule import ImportancePreferenceRule, PreferenceContext, ThresholdPreferenceRule
from src.feedback.event_types import FeedbackEventType
from src.feedback.metadata import PreferenceRuleMetadata
from src.feedback.models import FeedbackEvent, PreferenceObservation
from src.feedback.registry import register_preference_rule
from src.knowledge import knowledge_service

_POSITIVE_TYPES = frozenset(
    {FeedbackEventType.SAVED, FeedbackEventType.SHORTLISTED, FeedbackEventType.CONTACTED}
)
_NEGATIVE_TYPES = frozenset({FeedbackEventType.REJECTED, FeedbackEventType.IGNORED})


class PriceSensitivityRule(ImportancePreferenceRule):
    """How much price seems to drive this user's save/reject decisions, relative
    to the Knowledge Engine's own city-average price. Missing evidence (no
    apartment, no city average yet) honestly produces no observation — never a
    fabricated "not price sensitive" default.
    """

    preference_key = "price_sensitivity"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES | _NEGATIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.apartment is None or context.conn is None or context.location is None:
            return None
        average = knowledge_service.average_city_price(context.conn, context.location)
        if average is None or average <= 0:
            return None

        ratio = context.apartment.current_price / average
        if event.event_type in _POSITIVE_TYPES:
            direction = "supporting" if ratio <= 1.0 else "opposing"
        elif event.event_type in _NEGATIVE_TYPES:
            direction = "supporting" if ratio > 1.0 else None
            if direction is None:
                return None
        else:
            return None

        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction=direction, magnitude=min(1.0, abs(ratio - 1.0) + 0.3), source_type="inferred",
            computed_at=event.occurred_at,
            explanation=f"{event.event_type} at price ratio {ratio:.2f}x city average",
            observed_value={"price_ratio": ratio},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Price Sensitivity", category="cost",
            description="How strongly price relative to the city average drives this user's save/reject decisions.",
            value_shape="importance", relevant_event_types=self.relevant_event_types(),
        )


class MaximumBudgetRule(ThresholdPreferenceRule):
    """A decayed-weighted average of prices this user has positively engaged with
    (saved/shortlisted/contacted) — a real, honest proxy for "the price point this
    user seems comfortable around," not a literal maximum (a single expensive
    outlier wouldn't otherwise move a true max very informatively).
    """

    preference_key = "maximum_budget"

    def relevant_event_types(self) -> frozenset[str]:
        return _POSITIVE_TYPES

    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        if context.apartment is None:
            return None
        return PreferenceObservation(
            profile_id=event.profile_id, preference_key=self.preference_key, event_id=event.event_id,
            direction="supporting", magnitude=1.0, source_type="inferred", computed_at=event.occurred_at,
            explanation=f"{event.event_type} at ${context.apartment.current_price:.0f}/mo",
            observed_value={"value": context.apartment.current_price},
        )

    def metadata(self) -> PreferenceRuleMetadata:
        return PreferenceRuleMetadata(
            preference_key=self.preference_key, display_name="Maximum Budget", category="cost",
            description="A decayed-weighted average of prices this user has positively engaged with.",
            value_shape="threshold", relevant_event_types=self.relevant_event_types(),
        )


register_preference_rule(PriceSensitivityRule())
register_preference_rule(MaximumBudgetRule())
