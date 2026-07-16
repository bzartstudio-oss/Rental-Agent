"""Shared shapes for the Intelligent Ranking Engine — every rule's output and every
apartment's final ranking result uses one of these. See
docs/27_Intelligent_Ranking_Engine.md "Architecture".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RankingEvidence:
    """One rule's verdict on one apartment. `raw_score` is always in `[0.0, 1.0]`
    (higher is better) so every rule is comparable regardless of what it measures —
    `None` means this rule honestly has no evidence for this apartment (missing
    context, no accumulated history, ...), never a guessed midpoint value.
    `detail` is the human-readable sentence this rule contributes to the apartment's
    explanation (e.g. "8 min walk to city center") — written once, here, rather than
    reconstructed later from raw numbers.
    """

    rule_key: str
    raw_score: float | None
    confidence: float | None
    detail: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class RuleContribution:
    """How much one rule actually moved the final score — `evidence` is the rule's
    own verdict; `weight` is the *effective* weight this rule got after per-apartment
    renormalization (see `pipeline.py`); `weighted_score` is `weight * raw_score`,
    the actual number added into the final `[0, 100]` score.
    """

    rule_key: str
    evidence: RankingEvidence
    weight: float
    weighted_score: float


@dataclass
class RankingConfidence:
    """The apartment-level confidence rollup — a single number a report can show
    next to the score, plus the per-rule detail behind it (so "why is confidence
    only 0.6?" is always answerable).
    """

    overall: float | None
    per_rule: dict[str, float | None] = field(default_factory=dict)


@dataclass
class RankingExplanation:
    """A complete, human-readable account of one apartment's score — "Generate a
    complete explanation for every ranked apartment" (the mission's own words).
    `top_positive_factors`/`top_negative_factors` are `detail` strings from the
    highest-magnitude contributing rules, sorted so the most decisive reasons come
    first — exactly the mission's own example shape ("Excellent walking distance.
    Very reliable platform. ...").
    """

    apartment_id: str
    final_score: float
    confidence: RankingConfidence
    top_positive_factors: list[str] = field(default_factory=list)
    top_negative_factors: list[str] = field(default_factory=list)
    all_reasons: list[str] = field(default_factory=list)


@dataclass
class RankedApartmentV2:
    """One apartment's complete Ranking Engine V2 result — "Every score must
    return: Final Score, Confidence, Evidence, Rule Contributions, Warnings,
    Timestamp" (the mission's own words); every one of those is a field here.
    """

    apartment_id: str
    rank: int
    final_score: float
    confidence: RankingConfidence
    contributions: list[RuleContribution]
    explanation: RankingExplanation
    warnings: list[str]
    computed_at: datetime
