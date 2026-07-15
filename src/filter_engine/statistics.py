"""`FilterStatistics` — computed *from* a completed `FilterEngine.run()`'s results,
never inside `FilterEngine` itself (single responsibility: the engine filters, this
module describes the outcome — the same separation `analysis/scoring.py` keeps from
`analysis/engine.py`). See docs/25_Dynamic_Filter_Engine.md "Filter Pipeline".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.filter_engine.result import FilterResult


@dataclass
class FilterStatistics:
    total_apartments: int
    matched_count: int
    excluded_count: int
    match_rate: float | None
    # Per-filter-key fraction of apartments that individually passed *that* filter —
    # distinct from `match_rate` (the composed AND/OR/NOT outcome): a filter can have
    # a high individual pass rate while the overall search still excludes most
    # apartments, if it's ANDed with a much stricter one.
    per_filter_pass_rate: dict[str, float] = field(default_factory=dict)
    execution_time_ms: int | None = None

    def as_dict(self) -> dict:
        """JSON-safe shape for `filter_execution_history.statistics_json` — a plain
        dict, not a bespoke serializer, since every field here is already JSON-native.
        """
        return {
            "total_apartments": self.total_apartments,
            "matched_count": self.matched_count,
            "excluded_count": self.excluded_count,
            "match_rate": self.match_rate,
            "per_filter_pass_rate": self.per_filter_pass_rate,
            "execution_time_ms": self.execution_time_ms,
        }


def compute_filter_statistics(results: list[FilterResult], execution_time_ms: int | None = None) -> FilterStatistics:
    total = len(results)
    matched = sum(1 for result in results if result.matches)

    per_filter_votes: dict[str, list[bool]] = {}
    for result in results:
        for key, passed in result.per_filter.items():
            per_filter_votes.setdefault(key, []).append(passed)

    return FilterStatistics(
        total_apartments=total,
        matched_count=matched,
        excluded_count=total - matched,
        match_rate=(matched / total) if total else None,
        per_filter_pass_rate={key: sum(votes) / len(votes) for key, votes in per_filter_votes.items()},
        execution_time_ms=execution_time_ms,
    )
