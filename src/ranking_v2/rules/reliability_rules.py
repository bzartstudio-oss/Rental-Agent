"""`PlatformReliabilityRankingRule`/`ConnectorReliabilityRankingRule` — "Platform
Reliability" and "Connector Reliability" from the mission's INPUTS list. See
docs/27_Intelligent_Ranking_Engine.md "Rules".

Both read the Knowledge Engine's own accumulated rollups directly (`platform_reliability()`/
`connector_health()`, v2.0 Step 4) — neither recomputes a success rate or observation
count; both are only real once at least one search has actually observed this
apartment's platform.
"""

from __future__ import annotations

from src.knowledge import knowledge_service
from src.ranking_v2.base_rule import RankingContext, RankingRule
from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import RankingEvidence
from src.ranking_v2.registry import register_ranking_rule
from src.ranking_v2.rules._phrasing import qualitative
from src.storage.models import Apartment


class PlatformReliabilityRankingRule(RankingRule):
    rule_key = "platform_reliability"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Platform Reliability", category="trust",
            description="The Knowledge Engine's accumulated reliability score for this apartment's platform.",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        if context.conn is None:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        knowledge = knowledge_service.platform_reliability(context.conn, apartment.platform_id)
        if knowledge.reliability_score is None:
            return RankingEvidence(
                rule_key=self.rule_key, raw_score=None, confidence=None, detail=None,
                warnings=[f"No reliability rollup yet for platform {apartment.platform_id!r}"],
            )

        score = max(0.0, min(1.0, knowledge.reliability_score))
        detail = (
            f"{qualitative(score)} platform reliability: {score:.0%} "
            f"across {knowledge.observation_count} observation(s)"
        )
        return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=1.0, detail=detail)


class ConnectorReliabilityRankingRule(RankingRule):
    rule_key = "connector_reliability"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Connector Reliability", category="trust",
            description="This platform's connector's recent success rate (ConnectorHealth, Knowledge Engine).",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        if context.conn is None:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        health_records = knowledge_service.connector_health(context.conn, apartment.platform_id)
        if not health_records:
            return RankingEvidence(
                rule_key=self.rule_key, raw_score=None, confidence=None, detail=None,
                warnings=[f"No connector health observations yet for platform {apartment.platform_id!r}"],
            )

        health = health_records[0]
        total = health.success_count + health.failure_count
        if total == 0:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        score = health.success_count / total
        detail = f"{qualitative(score)} connector reliability: {health.success_count}/{total} recent runs succeeded"
        return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=1.0, detail=detail)


register_ranking_rule(PlatformReliabilityRankingRule())
register_ranking_rule(ConnectorReliabilityRankingRule())
