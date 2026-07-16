"""Adapts a `PreferenceProfile` into a *suggested* `RankingWeights`/`RankingProfile`
— "Integrate with RankingEngineV2 through a clear adapter or contribution
interface. Do not couple FeedbackEngine directly to individual ranking rules"
(the mission's own words). This module is the *only* place that knows both
`ranking_v2` and `feedback` exist — neither package imports the other; both are
imported here.

Only 5 of the 23 preference dimensions currently have a corresponding
`ranking_v2` rule_key (`price_sensitivity`→`price`, `walking_distance`,
`public_transport`, `availability_importance`→`availability`, `lifestyle`) — an
honest, documented limitation: the other 18 preferences (property type, amenities,
platform, ...) don't yet have a matching ranking rule to suggest a weight for, the
same "future modules" reasoning `docs/27_Intelligent_Ranking_Engine.md`'s own
"Which future modules will depend on this engine" section already used. See
docs/28_User_Feedback_and_Preference_Learning.md "Ranking Integration".
"""

from __future__ import annotations

from src.feedback.models import FeedbackMode, PreferenceProfile
from src.ranking_v2 import RankingProfile, RankingWeights

# Confidence below this is too weak to suggest a ranking weight from — an
# inferred preference still building consistency shouldn't yet move real scoring
# suggestions. Explicit preferences bypass this threshold entirely (see
# `suggest_ranking_weights()`).
_MIN_CONFIDENCE_TO_SUGGEST = 0.4

# The only preference keys with a direct ranking_v2 rule_key counterpart today.
_PREFERENCE_TO_RANKING_RULE: dict[str, str] = {
    "price_sensitivity": "price",
    "walking_distance": "walking_distance",
    "public_transport": "public_transport",
    "availability_importance": "availability",
    "lifestyle": "lifestyle",
}


def suggest_ranking_weights(profile: PreferenceProfile, *, base_weights: RankingWeights | None = None) -> RankingWeights:
    """Starts from `base_weights` (if given) and overrides only the rule_keys this
    profile has sufficient evidence for — every other configured weight is left
    exactly as the caller supplied it.
    """
    values = dict(base_weights.values) if base_weights is not None else {}

    for preference_key, rule_key in _PREFERENCE_TO_RANKING_RULE.items():
        value = profile.preferences.get(preference_key)
        if value is None or value.current_value is None:
            continue
        importance = value.current_value.get("importance")
        if importance is None:
            continue
        if not value.is_explicit and value.confidence.overall < _MIN_CONFIDENCE_TO_SUGGEST:
            continue
        values[rule_key] = importance * 100  # same 0-100 percentage-style convention RankingWeights already uses

    return RankingWeights(values=values)


def suggest_ranking_profile(
    profile: PreferenceProfile, *, name: str = "suggested", base_weights: RankingWeights | None = None
) -> RankingProfile:
    weights = suggest_ranking_weights(profile, base_weights=base_weights)
    return RankingProfile(
        name=name, weights=weights,
        description=f"Suggested from preference profile {profile.profile_id!r} — not applied unless mode is ASSISTED.",
    )


def resolve_ranking_profile(
    preference_profile: PreferenceProfile, explicit_ranking_profile: RankingProfile,
) -> RankingProfile:
    """"Support three modes" (the mission's own words) — the single dispatch point
    every caller should use, so the mode's actual effect is decided in exactly one
    place. `EXPLICIT_ONLY`/`SUGGESTED` both return `explicit_ranking_profile`
    completely unchanged: `SUGGESTED` still lets a caller inspect
    `suggest_ranking_profile()` separately for display, it just never becomes what
    actually ranks anything — "generate suggested weights but do not apply them
    automatically" (the mission's own words). Only `ASSISTED` returns the
    suggestion, and even then seeded from the user's own explicit weights as a
    base (`base_weights=explicit_ranking_profile.weights`), so an ASSISTED profile
    still only *overrides* what the learned evidence actually covers.
    """
    if preference_profile.mode is FeedbackMode.ASSISTED:
        return suggest_ranking_profile(
            preference_profile, name=f"{explicit_ranking_profile.name}+assisted",
            base_weights=explicit_ranking_profile.weights,
        )
    return explicit_ranking_profile
