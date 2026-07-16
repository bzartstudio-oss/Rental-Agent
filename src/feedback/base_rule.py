"""`PreferenceRule` — the plugin contract every preference dimension implements —
and `PreferenceContext` — everything a rule may read beyond the raw event. See
docs/28_User_Feedback_and_Preference_Learning.md "Architecture"/"Preference
Calculation".

Four shared intermediate base classes (`ImportancePreferenceRule`/
`ThresholdPreferenceRule`/`CategoricalPreferenceRule`/`BooleanPreferenceRule`)
provide one real, shared `aggregate()` implementation each — the mission's own
"Learning Rules" section describes ONE consistent algorithm (decay, explicit-
outweighs-inferred, conflict reduces confidence, single actions don't swing the
profile), so a concrete rule only ever implements `observe()` (the one thing that
genuinely differs per preference dimension: which event types it reads and what
evidence it extracts), never re-deriving that shared math — mirrors the
"DormantBooleanFilter/DormantStringFilter/..." shared-base pattern
`filter_engine/filters/dormant_base.py` already established, generalized from
"share validation" to "share the entire aggregation algorithm."
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.feedback.decay import DecayConfig, compute_confidence, decayed_weight
from src.feedback.metadata import PreferenceRuleMetadata
from src.feedback.models import FeedbackEvent, PreferenceConfidence, PreferenceObservation, PreferenceValue
from src.geography.models import GeoEnrichment
from src.storage.models import Apartment


@dataclass
class PreferenceContext:
    conn: sqlite3.Connection | None = None
    apartment: Apartment | None = None
    geo_enrichment: GeoEnrichment | None = None
    location: str | None = None
    now: datetime | None = None
    decay_config: DecayConfig = field(default_factory=DecayConfig)

    def reference_time(self) -> datetime:
        return self.now or datetime.now(timezone.utc)


class PreferenceRule(ABC):
    preference_key: str

    @abstractmethod
    def relevant_event_types(self) -> frozenset[str]:
        """Which `FeedbackEvent.event_type` strings this rule ever reads —
        `FeedbackEngine` uses this to route events to rules without either side
        knowing about the other's internals.
        """
        raise NotImplementedError

    @abstractmethod
    def observe(self, event: FeedbackEvent, context: PreferenceContext) -> PreferenceObservation | None:
        """Returns `None` when this event — despite being a relevant type — carries
        no usable evidence for this rule (e.g. the apartment is missing the field
        this rule needs). "Missing evidence must not be treated as negative
        preference evidence" (the mission's own words): `None` here means "silent,"
        never a fabricated opposing observation.
        """
        raise NotImplementedError

    @abstractmethod
    def aggregate(self, observations: list[PreferenceObservation], context: PreferenceContext) -> PreferenceValue:
        raise NotImplementedError

    @abstractmethod
    def metadata(self) -> PreferenceRuleMetadata:
        raise NotImplementedError


def _explanation(observations: list[PreferenceObservation], confidence: PreferenceConfidence, value_desc: str) -> str:
    if not observations:
        return "No evidence yet"
    return (
        f"{value_desc} — {len(observations)} observation(s): {confidence.supporting_evidence_count} supporting, "
        f"{confidence.opposing_evidence_count} opposing ({confidence.explicit_count} explicit, "
        f"{confidence.inferred_count} inferred); confidence {confidence.overall:.2f}"
    )


def _empty_value(preference_key: str) -> PreferenceValue:
    return PreferenceValue(
        preference_key=preference_key, current_value=None,
        confidence=PreferenceConfidence(overall=0.0, supporting_evidence_count=0, opposing_evidence_count=0,
                                         explicit_count=0, inferred_count=0),
        source_types=set(), last_updated=None, explanation="No evidence yet",
    )


class ImportancePreferenceRule(PreferenceRule):
    """Shared aggregation for "how much does this dimension matter to the user"
    preferences — `current_value = {"importance": float}` in `[0, 1]`, the shape
    `src.feedback.ranking_adapter` reads directly to suggest a ranking weight.
    """

    def aggregate(self, observations: list[PreferenceObservation], context: PreferenceContext) -> PreferenceValue:
        if not observations:
            return _empty_value(self.preference_key)

        now = context.reference_time()
        confidence = compute_confidence(observations, now, context.decay_config)
        supporting = sum(decayed_weight(o, now, context.decay_config) for o in observations if o.direction == "supporting")
        opposing = sum(decayed_weight(o, now, context.decay_config) for o in observations if o.direction == "opposing")
        total = supporting + opposing
        importance = (supporting / total) if total > 0 else 0.5

        return PreferenceValue(
            preference_key=self.preference_key, current_value={"importance": importance}, confidence=confidence,
            source_types={o.source_type for o in observations}, last_updated=max(o.computed_at for o in observations),
            explanation=_explanation(observations, confidence, f"importance={importance:.2f}"),
            is_explicit=confidence.explicit_count > 0,
        )


class ThresholdPreferenceRule(PreferenceRule):
    """Shared aggregation for a preferred numeric target/limit — `current_value =
    {"preferred": float}`, a decayed-weighted average of every observation's own
    `observed_value["value"]`.
    """

    def aggregate(self, observations: list[PreferenceObservation], context: PreferenceContext) -> PreferenceValue:
        numeric = [o for o in observations if o.observed_value and "value" in o.observed_value]
        if not numeric:
            return _empty_value(self.preference_key)

        now = context.reference_time()
        confidence = compute_confidence(observations, now, context.decay_config)
        weights = [decayed_weight(o, now, context.decay_config) for o in numeric]
        total_weight = sum(weights)
        if total_weight > 0:
            preferred = sum(o.observed_value["value"] * w for o, w in zip(numeric, weights)) / total_weight
        else:
            preferred = sum(o.observed_value["value"] for o in numeric) / len(numeric)

        return PreferenceValue(
            preference_key=self.preference_key, current_value={"preferred": preferred}, confidence=confidence,
            source_types={o.source_type for o in observations}, last_updated=max(o.computed_at for o in observations),
            explanation=_explanation(observations, confidence, f"preferred value={preferred:.1f}"),
            is_explicit=confidence.explicit_count > 0,
        )


class CategoricalPreferenceRule(PreferenceRule):
    """Shared aggregation for a preferred category out of several — `current_value
    = {"preferred": str, "distribution": dict[str, float]}`, the leading category
    by decayed-weighted support plus the full distribution for transparency.
    """

    def aggregate(self, observations: list[PreferenceObservation], context: PreferenceContext) -> PreferenceValue:
        categorical = [
            o for o in observations if o.observed_value and "category" in o.observed_value and o.direction == "supporting"
        ]
        if not categorical:
            return _empty_value(self.preference_key)

        now = context.reference_time()
        confidence = compute_confidence(observations, now, context.decay_config)
        distribution: dict[str, float] = {}
        for o in categorical:
            weight = decayed_weight(o, now, context.decay_config)
            category = o.observed_value["category"]
            distribution[category] = distribution.get(category, 0.0) + weight
        preferred = max(distribution, key=distribution.get)

        return PreferenceValue(
            preference_key=self.preference_key,
            current_value={"preferred": preferred, "distribution": distribution}, confidence=confidence,
            source_types={o.source_type for o in observations}, last_updated=max(o.computed_at for o in observations),
            explanation=_explanation(observations, confidence, f"preferred={preferred!r}"),
            is_explicit=confidence.explicit_count > 0,
        )


class BooleanPreferenceRule(PreferenceRule):
    """Shared aggregation for "does the user want this amenity" preferences —
    `current_value = {"wants": bool, "strength": float}`. Used by the Group-B
    dimensions with no structured listing field to corroborate against (see
    `rules/amenity_rules.py`'s own docstring) — evidence here comes only from
    explicit filter selections/removals and manual ratings, never a listing
    outcome, and `metadata().learns_from_listing_fields` is `False` to document
    that honestly.
    """

    def aggregate(self, observations: list[PreferenceObservation], context: PreferenceContext) -> PreferenceValue:
        if not observations:
            return _empty_value(self.preference_key)

        now = context.reference_time()
        confidence = compute_confidence(observations, now, context.decay_config)
        supporting = sum(decayed_weight(o, now, context.decay_config) for o in observations if o.direction == "supporting")
        opposing = sum(decayed_weight(o, now, context.decay_config) for o in observations if o.direction == "opposing")
        total = supporting + opposing
        wants = supporting >= opposing
        strength = (max(supporting, opposing) / total) if total > 0 else 0.0

        return PreferenceValue(
            preference_key=self.preference_key, current_value={"wants": wants, "strength": strength},
            confidence=confidence, source_types={o.source_type for o in observations},
            last_updated=max(o.computed_at for o in observations),
            explanation=_explanation(observations, confidence, f"wants={wants} (strength={strength:.2f})"),
            is_explicit=confidence.explicit_count > 0,
        )
