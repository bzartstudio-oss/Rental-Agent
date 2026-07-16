"""The Intelligent Ranking Engine V2 — a modular, explainable, evidence-based
decision engine. See docs/27_Intelligent_Ranking_Engine.md.

Importing this package imports `ranking_v2.rules`, which is what runs every
built-in ranking rule's `register_ranking_rule(...)` call. Public API re-exported
here so callers don't need to know this package's internal file layout — mirrors
`src.filter_engine`/`src.geography`'s own re-export shape.
"""

from __future__ import annotations

from src.ranking_v2 import rules as _rules  # noqa: F401 — import for self-registration side effect
from src.ranking_v2.base_rule import RankingContext, RankingRule
from src.ranking_v2.engine import RankingEngineV2
from src.ranking_v2.exceptions import RankingConfigurationError, RankingEvaluationError, RankingException
from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import (
    RankedApartmentV2,
    RankingConfidence,
    RankingEvidence,
    RankingExplanation,
    RuleContribution,
)
from src.ranking_v2.pipeline import RankingPipeline
from src.ranking_v2.profile import COMPREHENSIVE_PROFILE, DEFAULT_PROFILE, RankingProfile
from src.ranking_v2.registry import RankingRuleRegistry, register_ranking_rule
from src.ranking_v2.statistics import RankingStatistics, compute_ranking_statistics
from src.ranking_v2.weights import RankingWeights

__all__ = [
    "RankingContext",
    "RankingRule",
    "RankingEngineV2",
    "RankingException",
    "RankingConfigurationError",
    "RankingEvaluationError",
    "RankingRuleMetadata",
    "RankedApartmentV2",
    "RankingConfidence",
    "RankingEvidence",
    "RankingExplanation",
    "RuleContribution",
    "RankingPipeline",
    "COMPREHENSIVE_PROFILE",
    "DEFAULT_PROFILE",
    "RankingProfile",
    "RankingRuleRegistry",
    "register_ranking_rule",
    "RankingStatistics",
    "compute_ranking_statistics",
    "RankingWeights",
]
