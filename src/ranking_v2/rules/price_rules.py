"""`PriceRankingRule`/`PriceHistoryRankingRule` — "Price" and "Price History"/
"Apartment History" from the mission's INPUTS list. See
docs/27_Intelligent_Ranking_Engine.md "Rules".
"""

from __future__ import annotations

from src.knowledge import knowledge_service
from src.ranking_v2.base_rule import RankingContext, RankingRule
from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import RankingEvidence
from src.ranking_v2.registry import register_ranking_rule
from src.ranking_v2.rules._phrasing import qualitative
from src.storage import apartment_repository
from src.storage.models import Apartment

_VERSION = "1.0.0"


class PriceRankingRule(RankingRule):
    """Real evidence from two places at once: `apartment.current_price` (always
    populated) and `knowledge_service.average_city_price()` — the Knowledge Engine's
    own accumulated rollup, reused directly rather than recomputed here. At or below
    the city average scores the maximum; double the average scores zero — a simple,
    documented, linear scale, not a hidden curve.
    """

    rule_key = "price"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Price", category="cost",
            description="Current price relative to the Knowledge Engine's average price for this city.",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        if context.conn is None or context.location is None:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        average = knowledge_service.average_city_price(context.conn, context.location)
        if average is None or average <= 0:
            return RankingEvidence(
                rule_key=self.rule_key, raw_score=None, confidence=None, detail=None,
                warnings=[f"No average price known yet for {context.location!r}"],
            )

        ratio = apartment.current_price / average
        score = max(0.0, min(1.0, 1.0 - (ratio - 1.0)))
        pct = (ratio - 1.0) * 100

        return RankingEvidence(
            rule_key=self.rule_key, raw_score=score, confidence=1.0,
            detail=f"{qualitative(score)} price: ${apartment.current_price:.0f}/mo vs "
                   f"${average:.0f}/mo city average ({pct:+.0f}%)",
        )


class PriceHistoryRankingRule(RankingRule):
    """Real evidence from `apartment_price_history` (Apartment History Engine,
    v2.0 Step 2). Needs at least two observations to have a trend to describe — one
    observation is a snapshot, not a history.
    """

    rule_key = "price_trend"

    def metadata(self) -> RankingRuleMetadata:
        return RankingRuleMetadata(
            rule_key=self.rule_key, display_name="Price Trend", category="cost",
            description="Whether this apartment's price has dropped, held, or risen since first observed.",
            requires_context=True,
        )

    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        if context.conn is None:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        history = apartment_repository.get_price_history(context.conn, apartment.id)
        if len(history) < 2:
            return RankingEvidence(
                rule_key=self.rule_key, raw_score=None, confidence=None, detail=None,
                warnings=["Fewer than two price observations — no trend yet"],
            )

        first_price, last_price = history[0].price, history[-1].price
        if first_price <= 0:
            return RankingEvidence(rule_key=self.rule_key, raw_score=None, confidence=None, detail=None)

        change_pct = (last_price - first_price) / first_price * 100

        if last_price < first_price:
            score = max(0.6, min(1.0, 0.6 + abs(change_pct) / 25))
            detail = f"Price dropped {abs(change_pct):.0f}% since first observed"
        elif last_price > first_price:
            score = max(0.0, 0.5 - change_pct / 25)
            detail = f"Price increased {change_pct:.0f}% since first observed"
        else:
            score = 0.6
            detail = "Price has been stable since first observed"

        return RankingEvidence(rule_key=self.rule_key, raw_score=score, confidence=1.0, detail=detail)


register_ranking_rule(PriceRankingRule())
register_ranking_rule(PriceHistoryRankingRule())
