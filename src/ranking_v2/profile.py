"""`RankingProfile` — a named, reusable `RankingWeights` preset. See
docs/27_Intelligent_Ranking_Engine.md "User Priorities".

Two built-in profiles ship with this engine — `DEFAULT_PROFILE` (the mission's own
worked example: Price 40%, Walking Distance 25%, Availability 15%, Public Transport
10%, Lifestyle 10%) and `COMPREHENSIVE_PROFILE` (every registered rule weighted
equally) — proving two genuinely different user priorities produce genuinely
different orderings over the same apartments, per this sprint's own "Demonstrate
ranking with multiple apartments using different user priorities" requirement. A
caller is never limited to these two: `RankingProfile(name=..., weights=RankingWeights(...))`
builds any custom profile directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.ranking_v2.weights import RankingWeights


@dataclass
class RankingProfile:
    name: str
    weights: RankingWeights
    description: str = ""


DEFAULT_PROFILE = RankingProfile(
    name="default",
    description="The mission's own worked example: price-led, with a strong location component.",
    weights=RankingWeights(
        values={
            "price": 40,
            "walking_distance": 25,
            "availability": 15,
            "public_transport": 10,
            "lifestyle": 10,
        }
    ),
)

COMPREHENSIVE_PROFILE = RankingProfile(
    name="comprehensive",
    description="Every registered rule weighted equally — a neutral profile that surfaces every kind of evidence.",
    weights=RankingWeights(
        values={
            "price": 1,
            "price_trend": 1,
            "walking_distance": 1,
            "public_transport": 1,
            "availability": 1,
            "lifestyle": 1,
            "filter_preferences": 1,
            "analysis_composite": 1,
            "platform_reliability": 1,
            "connector_reliability": 1,
            "provider_health": 1,
            "search_history": 1,
        }
    ),
)
