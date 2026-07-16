"""`RankingEngineV2` — the outward-facing entry point: apartments + a
`RankingProfile` in, a fully explained, deterministically ordered ranking out. See
docs/27_Intelligent_Ranking_Engine.md "Architecture".

Deliberately does not hard-filter apartments itself — that's the Dynamic Filter
Engine's (or `search.criteria.apply_filters()`'s) job, already done before this
engine ever runs, the same "don't redesign an already-working prior stage" reasoning
already applied to the Filter Engine's and Geographic Engine's own integration.
`RankingEngineV2.rank()` assumes every apartment it's given is already a valid
candidate; its only job is scoring and explaining, matching `RankingPipeline`'s own
single responsibility.
"""

from __future__ import annotations

from src.ranking_v2.base_rule import RankingContext
from src.ranking_v2.models import RankedApartmentV2
from src.ranking_v2.pipeline import RankingPipeline
from src.ranking_v2.profile import DEFAULT_PROFILE, RankingProfile
from src.storage.models import Apartment


class RankingEngineV2:
    def __init__(self, profile: RankingProfile | None = None) -> None:
        self.profile = profile or DEFAULT_PROFILE

    def rank(self, apartments: list[Apartment], context: RankingContext | None = None) -> list[RankedApartmentV2]:
        """Sorted best-first by `final_score`; ties broken by original input order
        (Python's sort is stable) — the same determinism guarantee `RankingEngine`
        (v1) and `FilterEngine` already give.
        """
        context = context or RankingContext()
        pipeline = RankingPipeline(self.profile.weights)

        results = [pipeline.rank_one(apartment, context) for apartment in apartments]
        results.sort(key=lambda entry: entry.final_score, reverse=True)

        for index, entry in enumerate(results):
            entry.rank = index + 1

        return results
