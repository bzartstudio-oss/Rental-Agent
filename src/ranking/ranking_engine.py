"""RankingEngine — see docs/08_Ranking_System.md. Filters apartments against a
SearchRequest's hard criteria, scores the survivors, and returns them ordered best-first.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.ranking.scoring import score_apartment
from src.search.criteria import apply_filters
from src.search.search_request import SearchRequest
from src.storage.models import Apartment


@dataclass
class RankedApartment:
    apartment: Apartment
    rank: int
    score: float
    score_breakdown: dict


class RankingEngine:
    def rank(self, apartments: list[Apartment], request: SearchRequest) -> list[RankedApartment]:
        matching = apply_filters(apartments, request.criteria)

        scored = [(apartment, *score_apartment(apartment, request.criteria)) for apartment in matching]
        scored.sort(key=lambda entry: entry[1], reverse=True)

        return [
            RankedApartment(apartment=apartment, rank=index + 1, score=score, score_breakdown=breakdown)
            for index, (apartment, score, breakdown) in enumerate(scored)
        ]
