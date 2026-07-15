"""Pure scoring functions for provider selection — no provider/registry/router
imports here, matching the existing "weights are data, not hardcoded logic" convention
(`src/ranking/scoring.py`, `src/analysis/scoring.py`). See
docs/21_Provider_Abstraction_Layer.md "Scoring Model".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderMetadata:
    """A provider's static self-description, returned by `Provider.metadata()`.

    `cost_score`/`freshness_score`/`quality_score` are each in `[0, 1]`. `cost_score`
    is the only "lower is better" one (0 = free/cheap, 1 = expensive) — inverted in
    `score_provider()` so every component of the final score is "higher is better,"
    consistent with `freshness_score`/`quality_score`.
    """

    provider_id: str
    cost_score: float
    freshness_score: float
    quality_score: float
    description: str = ""


@dataclass(frozen=True)
class ScoringWeights:
    """Weights for the four factors the mission names explicitly: availability, cost,
    freshness, quality. Conventionally sums to `1.0` (not enforced — a caller
    overriding weights is trusted to keep the score interpretable) so a total score
    stays a `[0, 1]`-ish figure, not because the math requires it.
    """

    availability: float = 0.1
    cost: float = 0.25
    freshness: float = 0.3
    quality: float = 0.35


DEFAULT_WEIGHTS = ScoringWeights()


@dataclass(frozen=True)
class ProviderScore:
    """The full, itemized result of scoring one provider — kept itemized (not just a
    `total` float) so `ProviderRouter`'s logging can show *why* a provider ranked where
    it did, per-factor, not just its final number.
    """

    provider_id: str
    total: float
    availability_component: float
    cost_component: float
    freshness_component: float
    quality_component: float


def score_provider(
    metadata: ProviderMetadata,
    available: bool,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
) -> ProviderScore:
    """`available` is passed in separately from `metadata` (rather than being a field
    on `ProviderMetadata`) because it's a dynamic, per-call fact (`Provider.is_available()`
    can change from one routing decision to the next — an env var gets set, a local
    service comes up), while `ProviderMetadata` is a provider's fixed, static
    self-description. Availability is scored honestly here (contributing its full
    weight whenever `available=True`) but `ProviderRouter` never scores an unavailable
    provider at all — it's excluded from candidacy before this function is called, so
    an unavailable provider's other-dimension strengths can never make it "win" a
    ranking it was never eligible for.
    """
    availability_component = weights.availability * (1.0 if available else 0.0)
    cost_component = weights.cost * (1.0 - metadata.cost_score)
    freshness_component = weights.freshness * metadata.freshness_score
    quality_component = weights.quality * metadata.quality_score

    return ProviderScore(
        provider_id=metadata.provider_id,
        total=availability_component + cost_component + freshness_component + quality_component,
        availability_component=availability_component,
        cost_component=cost_component,
        freshness_component=freshness_component,
        quality_component=quality_component,
    )
