"""`AvailabilityRankingRule` — "Availability" from the mission's INPUTS list. See
docs/27_Intelligent_Ranking_Engine.md "Rules".
"""

from __future__ import annotations

from src.ranking_v2.base_rule import RankingContext, RankingRule
from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import RankingEvidence
from src.ranking_v2.registry import register_ranking_rule
from src.storage.models import Apartment

_AVAILABLE_STATUSES = {"available"}


class AvailabilityRankingRule(RankingRule):
    """`Apartment.current_status` is never `None` (populated by every connector's
    normalizer), so this is the one rule in this engine with unconditionally real
    evidence — confidence is always `1.0`.
    """

    rule_key = "availability"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Availability", category="logistics",
            description="Whether this apartment's most recently observed status is available.",
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        is_available = apartment.current_status in _AVAILABLE_STATUSES
        score = 1.0 if is_available else 0.0
        detail = "Availability confirmed" if is_available else f"Currently {apartment.current_status}"
        return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=1.0, detail=detail)


register_ranking_rule(AvailabilityRankingRule())
