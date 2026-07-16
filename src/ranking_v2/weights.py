"""`RankingWeights` — how much each rule's score matters, user-configurable. See
docs/27_Intelligent_Ranking_Engine.md "User Priorities".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.ranking_v2.exceptions import RankingConfigurationError


@dataclass
class RankingWeights:
    """A plain `rule_key -> weight` map. Weights need not sum to 1 — the mission's
    own example ("Price 40%, Walking Distance 25%, ...") is written as percentages
    of an implied whole, so raw values like `{"price": 40, "walking_distance": 25}`
    are accepted directly and normalized on read (`normalized()`), not forced into
    `[0, 1]` up front. A rule_key with no entry here simply gets weight `0.0` — it
    still runs and appears in the explanation with zero contribution, it just never
    moves the final score.
    """

    values: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key, value in self.values.items():
            if value < 0:
                raise RankingConfigurationError(f"RankingWeights: {key!r} has a negative weight ({value})")

    def get(self, rule_key: str) -> float:
        return self.values.get(rule_key, 0.0)

    def normalized(self) -> dict[str, float]:
        """Every configured weight divided by the sum of all configured weights —
        `{"price": 40, "walking_distance": 25, ...}` becomes `{"price": 0.4143, ...}`.
        An all-zero (or empty) `RankingWeights` normalizes to all zeros rather than
        raising or dividing by zero — every rule then honestly contributes nothing,
        a real and valid configuration (e.g. while only running rules for their
        evidence/explanation, not their effect on order).
        """
        total = sum(self.values.values())
        if total <= 0:
            return {key: 0.0 for key in self.values}
        return {key: value / total for key, value in self.values.items()}
