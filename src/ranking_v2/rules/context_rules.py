"""`FilterPreferenceRankingRule`/`AnalysisCompositeRankingRule`/`ProviderHealthRankingRule`/
`SearchHistoryRankingRule` — "Dynamic Filters", "Analysis Results", "Provider Health",
and "Search History" from the mission's INPUTS list. See
docs/27_Intelligent_Ranking_Engine.md "Rules".

All four are honestly dormant unless the caller supplies the matching optional
`RankingContext` field for a given run — the same "real, registered, tested, honest
about missing evidence" pattern the Dynamic Filter Engine's dormant filters already
established (v2.5 Step 9), applied here to whole upstream engines rather than
missing schema fields.
"""

from __future__ import annotations

from src.ranking_v2.base_rule import RankingContext, RankingRule
from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import RankingEvidence
from src.ranking_v2.registry import register_ranking_rule
from src.ranking_v2.rules._phrasing import qualitative
from src.storage.models import Apartment

# A flat, documented confidence constant for composite analysis scores: `CompositeScore`
# doesn't carry its own confidence value (it's a weighted average of possibly
# mixed-confidence analyzer results — see `analysis/models.py`), so this reflects
# moderate, not full, trust in an aggregate — the same honest-constant convention
# `nearby_amenity.py`'s `0.8` already established for a different kind of evidence.
_COMPOSITE_CONFIDENCE = 0.7


class FilterPreferenceRankingRule(RankingRule):
    """Reads `context.filter_results` — a `dict[apartment_id, FilterResult]` from an
    already-run `FilterEngine` pass over *soft* preference criteria, distinct from
    the hard constraints already applied before ranking ever runs (an apartment that
    failed a hard filter is never a ranking candidate at all). `FilterResult.per_filter`
    is reused directly, not recomputed.
    """

    rule_key = "filter_preferences"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Filter Preferences", category="preferences",
            description="Fraction of soft/preference filters this apartment matches (Dynamic Filter Engine).",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        result = context.filter_results.get(apartment.id)
        if result is None or not result.per_filter:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        matched = sum(1 for passed in result.per_filter.values() if passed)
        total = len(result.per_filter)
        score = matched / total
        detail = f"Matches {matched}/{total} preference filter(s)"
        return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=1.0, detail=detail)


class AnalysisCompositeRankingRule(RankingRule):
    """Reads `context.analysis_results` — this run's own `dict[apartment_id,
    AnalysisResult]` from the Deep Analysis Engine (v2.0 Step 6). Averages every
    composite score that has evidence; a composite with `score=None` (no component
    analyzer had evidence) is excluded, never treated as zero.
    """

    rule_key = "analysis_composite"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Analysis Composite", category="location",
            description="Average of this apartment's Deep Analysis Engine composite scores.",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        result = context.analysis_results.get(apartment.id)
        if result is None:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        scored = [composite for composite in result.composite_scores if composite.score is not None]
        if not scored:
            return RankingEvidence(
                rule_key=self.rule_key, raw_score=None, confidence=None, detail=None,
                warnings=["No analysis composite score had evidence"],
            )

        score = sum(composite.score for composite in scored) / len(scored)
        names = ", ".join(f"{composite.name}: {composite.score:.2f}" for composite in scored)
        detail = f"{qualitative(score)} analysis composite ({names})"
        return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=_COMPOSITE_CONFIDENCE, detail=detail)


class ProviderHealthRankingRule(RankingRule):
    """Reads `context.provider_health` — a `dict[platform_id, ProviderHealth]`
    snapshot taken once per run (a platform's provider health doesn't vary by
    listing), from `src.providers.health.check_provider_health()` (v2.5 Step 8).
    """

    rule_key = "provider_health"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Provider Health", category="trust",
            description="Whether this apartment's platform's data provider is currently available.",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        health = context.provider_health.get(apartment.platform_id)
        if health is None:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        score = 1.0 if health.is_available_now else 0.0
        detail = "Provider currently available" if health.is_available_now else "Provider currently unavailable"
        return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=1.0, detail=detail)


class SearchHistoryRankingRule(RankingRule):
    """Reads `context.search_comparison` — one whole-run `SearchComparison` against
    the previous search for this location, if the caller computed one (Search
    Memory, v2.0 Step 3). Only reports something for an apartment that actually
    appears in that comparison's `price_changes`/`new_apartment_ids` — everything
    else honestly has no search-history evidence this run.
    """

    rule_key = "search_history"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Search History", category="trust",
            description="Price movement or newly-discovered status since the previous search for this location.",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        comparison = context.search_comparison
        if comparison is None:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        for change in comparison.price_changes:
            if change.apartment_id != apartment.id or change.old_price is None or change.new_price is None:
                continue
            if change.new_price < change.old_price:
                score = 1.0
                detail = f"Price dropped from ${change.old_price:.0f} to ${change.new_price:.0f} since last search"
            elif change.new_price > change.old_price:
                score = 0.0
                detail = f"Price rose from ${change.old_price:.0f} to ${change.new_price:.0f} since last search"
            else:
                score = 0.6
                detail = "Price unchanged since last search"
            return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=1.0, detail=detail)

        if apartment.id in comparison.new_apartment_ids:
            return RankingEvidence(
                rule_key=self.rule_key, raw_score=0.6, confidence=1.0,
                detail="Newly discovered since the previous search",
            )

        return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)


register_ranking_rule(FilterPreferenceRankingRule())
register_ranking_rule(AnalysisCompositeRankingRule())
register_ranking_rule(ProviderHealthRankingRule())
register_ranking_rule(SearchHistoryRankingRule())
