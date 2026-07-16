"""`RankingPipeline` — the deterministic scoring core: run every registered rule ->
per-apartment weight renormalization -> weighted score -> confidence rollup ->
explanation. See docs/27_Intelligent_Ranking_Engine.md "Architecture"/"Explainability".

Renormalization is the key honesty mechanism here: a rule with no evidence for a
given apartment (missing optional context, no accumulated history, ...) is excluded
from *both* the numerator and the weight-normalization denominator for that specific
apartment, rather than silently counting as a zero. An apartment nobody has computed
`GeoEnrichment` for is never punished for missing "Walking Distance" evidence that
was never asked for in this run — its other, real evidence is reweighted to fill
the full 100%. This is what makes the engine "evidence-based" rather than
penalizing absent optional context as if it were bad news.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.ranking_v2.base_rule import RankingContext
from src.ranking_v2.models import (
    RankedApartmentV2,
    RankingConfidence,
    RankingExplanation,
    RuleContribution,
)
from src.ranking_v2.registry import RankingRuleRegistry
from src.ranking_v2.weights import RankingWeights
from src.storage.models import Apartment

_POSITIVE_THRESHOLD = 0.6
_NEGATIVE_THRESHOLD = 0.4
_MAX_FACTORS = 5


class RankingPipeline:
    def __init__(self, weights: RankingWeights) -> None:
        self.weights = weights

    def rank_one(self, apartment: Apartment, context: RankingContext) -> RankedApartmentV2:
        """Runs every registered rule, in registration order (deterministic, the
        same guarantee `FilterEngine.run_group()` already gives its own filters),
        against this one apartment.
        """
        computed_at = context.computed_at or datetime.now(timezone.utc)
        evidences = [rule.evaluate(apartment, context) for rule in RankingRuleRegistry.all()]

        configured = self.weights.normalized()
        weight_sum = sum(configured.get(ev.rule_key, 0.0) for ev in evidences if ev.raw_score is not None)

        contributions: list[RuleContribution] = []
        warnings: list[str] = []

        for ev in evidences:
            warnings.extend(ev.warnings)
            if ev.raw_score is not None and weight_sum > 0:
                effective_weight = configured.get(ev.rule_key, 0.0) / weight_sum
            else:
                effective_weight = 0.0
            weighted_score = effective_weight * ev.raw_score if ev.raw_score is not None else 0.0
            contributions.append(
                RuleContribution(rule_key=ev.rule_key, evidence=ev, weight=effective_weight, weighted_score=weighted_score)
            )

        if weight_sum <= 0:
            warnings.append("No weighted evidence available for this apartment under the current profile")

        final_score = sum(c.weighted_score for c in contributions) * 100
        confidence = _build_confidence(contributions)
        explanation = _build_explanation(apartment.id, final_score, confidence, contributions)

        return RankedApartmentV2(
            apartment_id=apartment.id,
            rank=0,  # assigned by RankingEngineV2 after sorting the whole set
            final_score=final_score,
            confidence=confidence,
            contributions=contributions,
            explanation=explanation,
            warnings=warnings,
            computed_at=computed_at,
        )


def _build_confidence(contributions: list[RuleContribution]) -> RankingConfidence:
    per_rule = {c.rule_key: c.evidence.confidence for c in contributions}
    weighted = [(c.evidence.confidence, c.weight) for c in contributions if c.weight > 0 and c.evidence.confidence is not None]

    if not weighted:
        return RankingConfidence(overall=None, per_rule=per_rule)

    total_weight = sum(w for _, w in weighted)
    overall = sum(conf * w for conf, w in weighted) / total_weight if total_weight > 0 else None
    return RankingConfidence(overall=overall, per_rule=per_rule)


def _build_explanation(
    apartment_id: str,
    final_score: float,
    confidence: RankingConfidence,
    contributions: list[RuleContribution],
) -> RankingExplanation:
    contributing = [c for c in contributions if c.weight > 0 and c.evidence.detail]

    positive = sorted(
        (c for c in contributing if c.evidence.raw_score is not None and c.evidence.raw_score >= _POSITIVE_THRESHOLD),
        key=lambda c: c.weighted_score,
        reverse=True,
    )
    negative = sorted(
        (c for c in contributing if c.evidence.raw_score is not None and c.evidence.raw_score <= _NEGATIVE_THRESHOLD),
        key=lambda c: c.weight * (1 - c.evidence.raw_score),
        reverse=True,
    )
    all_ordered = sorted(contributing, key=lambda c: c.weighted_score, reverse=True)

    return RankingExplanation(
        apartment_id=apartment_id,
        final_score=final_score,
        confidence=confidence,
        top_positive_factors=[c.evidence.detail for c in positive[:_MAX_FACTORS]],
        top_negative_factors=[c.evidence.detail for c in negative[:_MAX_FACTORS]],
        all_reasons=[c.evidence.detail for c in all_ordered],
    )
