"""`RankingStatistics` — computed *from* a completed `RankingEngineV2.rank()`'s
results, never inside the engine itself (single responsibility, the same separation
`filter_engine/statistics.py`/`geography/statistics.py` keep from their own engines).
See docs/27_Intelligent_Ranking_Engine.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.ranking_v2.models import RankedApartmentV2


@dataclass
class RankingStatistics:
    total_apartments: int
    average_score: float | None
    average_confidence: float | None
    # Fraction of apartments for which each rule produced real evidence (not None) —
    # the coverage picture a maintainer needs before trusting a profile's weights.
    rule_coverage: dict[str, float] = field(default_factory=dict)
    # Average raw_score per rule, among apartments where that rule had evidence.
    average_score_by_rule: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        """JSON-safe shape — a plain dict, not a bespoke serializer, since every
        field here is already JSON-native.
        """
        return {
            "total_apartments": self.total_apartments,
            "average_score": self.average_score,
            "average_confidence": self.average_confidence,
            "rule_coverage": self.rule_coverage,
            "average_score_by_rule": self.average_score_by_rule,
        }


def compute_ranking_statistics(ranked: list[RankedApartmentV2]) -> RankingStatistics:
    total = len(ranked)
    if total == 0:
        return RankingStatistics(total_apartments=0, average_score=None, average_confidence=None)

    scores = [entry.final_score for entry in ranked]
    confidences = [entry.confidence.overall for entry in ranked if entry.confidence.overall is not None]

    votes: dict[str, list[bool]] = {}
    score_sums: dict[str, list[float]] = {}
    for entry in ranked:
        for contribution in entry.contributions:
            has_evidence = contribution.evidence.raw_score is not None
            votes.setdefault(contribution.rule_key, []).append(has_evidence)
            if has_evidence:
                score_sums.setdefault(contribution.rule_key, []).append(contribution.evidence.raw_score)

    return RankingStatistics(
        total_apartments=total,
        average_score=sum(scores) / total,
        average_confidence=(sum(confidences) / len(confidences)) if confidences else None,
        rule_coverage={key: sum(v) / len(v) for key, v in votes.items()},
        average_score_by_rule={key: sum(v) / len(v) for key, v in score_sums.items()},
    )
