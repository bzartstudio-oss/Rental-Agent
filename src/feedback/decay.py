"""Shared decay/confidence math — the one consistent algorithm every preference
rule's `aggregate()` uses, so "deterministic and explainable" (the mission's own
words) means the same thing everywhere rather than 23 subtly different formulas.
See docs/28_User_Feedback_and_Preference_Learning.md "Confidence Model".

Every constant here is documented and passed as a parameter with a sensible
default — "the decay rule must be configurable" (the mission's own words) is
implemented by `DecayConfig` being a real, overridable dataclass, not a hidden
module-level number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.feedback.models import PreferenceConfidence, PreferenceObservation

# How much total decayed-weighted evidence is needed before confidence's "volume"
# component saturates at 1.0 — chosen so a single strong explicit observation
# (weight ~3.0 with the default multiplier) contributes well under full confidence
# on its own, satisfying "a single action must not strongly alter the profile."
_DEFAULT_SATURATION_WEIGHT = 5.0


@dataclass
class DecayConfig:
    """`half_life_days`: after this many days, an observation's weight halves —
    "recent behavior may be weighted more than very old behavior" (the mission's
    own words). `explicit_weight_multiplier`: how much more an explicit observation
    counts than an inferred one of the same magnitude — "explicit manual weight
    changes must count more strongly than inferred behavior."
    """

    half_life_days: float = 30.0
    explicit_weight_multiplier: float = 3.0
    saturation_weight: float = _DEFAULT_SATURATION_WEIGHT


DEFAULT_DECAY_CONFIG = DecayConfig()


def decayed_weight(observation: PreferenceObservation, now: datetime, decay_config: DecayConfig) -> float:
    """A single observation's contribution after age-decay and explicit/inferred
    weighting — always `>= 0`. `magnitude` itself is left untouched (a rule's own
    per-event evidence strength), only the *weight* this observation carries in
    aggregation is decayed.
    """
    age_days = max(0.0, (now - observation.computed_at).total_seconds() / 86400)
    time_factor = 0.5 ** (age_days / decay_config.half_life_days) if decay_config.half_life_days > 0 else 1.0
    source_multiplier = (
        decay_config.explicit_weight_multiplier if observation.source_type == "explicit" else 1.0
    )
    return time_factor * source_multiplier * observation.magnitude


def compute_confidence(
    observations: list[PreferenceObservation], now: datetime, decay_config: DecayConfig = DEFAULT_DECAY_CONFIG
) -> PreferenceConfidence:
    """`overall = consistency * volume` — `consistency` (`0` fully conflicting to
    `1` fully one-directional) implements "conflicting behavior must reduce
    confidence"; `volume` (saturating with more decayed-weighted evidence)
    implements "a single action must not strongly alter the profile." Both are
    `0.0` with no observations at all — an honest "no confidence," not a
    fabricated default.
    """
    supporting_weight = sum(decayed_weight(o, now, decay_config) for o in observations if o.direction == "supporting")
    opposing_weight = sum(decayed_weight(o, now, decay_config) for o in observations if o.direction == "opposing")
    total_weight = supporting_weight + opposing_weight

    if total_weight <= 0:
        consistency = 0.0
    else:
        consistency = abs(supporting_weight - opposing_weight) / total_weight

    volume = min(1.0, total_weight / decay_config.saturation_weight) if decay_config.saturation_weight > 0 else 1.0
    overall = consistency * volume

    return PreferenceConfidence(
        overall=overall,
        supporting_evidence_count=sum(1 for o in observations if o.direction == "supporting"),
        opposing_evidence_count=sum(1 for o in observations if o.direction == "opposing"),
        explicit_count=sum(1 for o in observations if o.source_type == "explicit"),
        inferred_count=sum(1 for o in observations if o.source_type == "inferred"),
    )
