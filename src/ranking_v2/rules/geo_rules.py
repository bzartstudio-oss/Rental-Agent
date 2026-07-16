"""`WalkingDistanceRankingRule`/`PublicTransportRankingRule`/`LifestyleRankingRule` —
"Geographic Intelligence" from the mission's INPUTS list, split into the three named
weight categories the mission's own worked example uses ("Walking Distance",
"Public Transport", "Lifestyle"). See docs/27_Intelligent_Ranking_Engine.md "Rules".

All three read `context.geo_enrichments` (this run's own `dict[apartment_id,
GeoEnrichment]`, computed by `GeographicEngine` — v2.5 Step 10) — none recompute a
single distance or nearby count themselves, reusing that engine's output exactly as
produced, including its own honestly-lower confidence for estimated travel times.
"""

from __future__ import annotations

from src.geography.models import TravelMode
from src.ranking_v2.base_rule import RankingContext, RankingRule
from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import RankingEvidence
from src.ranking_v2.registry import register_ranking_rule
from src.ranking_v2.rules._phrasing import qualitative
from src.storage.models import Apartment

# Travel time at or below this scores the maximum; at or beyond this scores zero —
# documented, tunable constants, not hidden numbers.
_MAX_SCORED_MINUTES = {TravelMode.WALKING: 45.0, TravelMode.PUBLIC_TRANSPORT: 45.0}


def _travel_time_score(minutes: float, max_minutes: float) -> float:
    return max(0.0, min(1.0, 1.0 - minutes / max_minutes))


class _TravelModeRankingRule(RankingRule):
    """Shared evaluation for the two travel-time rules — only `rule_key`/`_mode`/
    `_label` differ between `WalkingDistanceRankingRule` and
    `PublicTransportRankingRule`.
    """

    _mode: TravelMode
    _label: str

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        enrichment = context.geo_enrichments.get(apartment.id)
        if enrichment is None:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        result = enrichment.distances.get(self._mode)
        if result is None or result.travel_time_minutes is None:
            return RankingEvidence(
                rule_key=self.rule_key, raw_score=None, confidence=None, detail=None,
                warnings=[f"No {self._label.lower()} evidence for this apartment"],
            )

        score = _travel_time_score(result.travel_time_minutes, _MAX_SCORED_MINUTES[self._mode])
        detail = f"{qualitative(score)} {self._label.lower()}: {result.travel_time_minutes:.0f} min"
        return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=result.confidence, detail=detail)


class WalkingDistanceRankingRule(_TravelModeRankingRule):
    rule_key = "walking_distance"
    _mode = TravelMode.WALKING
    _label = "Walking distance"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Walking Distance", category="location",
            description="Estimated walking time to the location's reference point (GeographicEngine).",
            requires_context=True,
        )


class PublicTransportRankingRule(_TravelModeRankingRule):
    rule_key = "public_transport"
    _mode = TravelMode.PUBLIC_TRANSPORT
    _label = "Public transport"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Public Transport", category="location",
            description="Estimated public transport time to the location's reference point (GeographicEngine).",
            requires_context=True,
        )


class LifestyleRankingRule(RankingRule):
    """Rewards *confirmed* nearby-amenity coverage — categories with no curated
    evidence are excluded from the average entirely (never penalized), matching
    `GeographicEngine`'s own "no evidence" honesty rather than treating an absent
    curated fact as "zero nearby amenities."
    """

    rule_key = "lifestyle"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Lifestyle", category="location",
            description="Confirmed nearby-amenity coverage (supermarkets, parks, gyms, ...) from GeographicEngine.",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        enrichment = context.geo_enrichments.get(apartment.id)
        if enrichment is None or not enrichment.nearby:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        confirmed = []
        for category, places in enrichment.nearby.items():
            for place in places:
                if place.count is not None:
                    confirmed.append((category, place.count, place.confidence))

        if not confirmed:
            return RankingEvidence(
                rule_key=self.rule_key, raw_score=None, confidence=None, detail=None,
                warnings=["No curated nearby-amenity data confirmed for this location yet"],
            )

        per_category_score = [min(1.0, count / 5) for _, count, _ in confirmed]
        score = sum(per_category_score) / len(per_category_score)
        confidence = sum(c for _, _, c in confirmed if c is not None) / len(confirmed)
        names = ", ".join(category for category, _, _ in confirmed[:3])

        return RankingEvidence(
            rule_key=self.rule_key, raw_score=score, confidence=confidence,
            detail=f"{qualitative(score)} lifestyle fit: {len(confirmed)} nearby categories confirmed ({names})",
        )


register_ranking_rule(WalkingDistanceRankingRule())
register_ranking_rule(PublicTransportRankingRule())
register_ranking_rule(LifestyleRankingRule())
