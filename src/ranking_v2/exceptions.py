"""Structured exceptions for the Intelligent Ranking Engine — mirrors
`src.filter_engine.exceptions`/`src.geography.exceptions`'s "one base class, catch
one type" shape, applied to ranking rules and weights. See
docs/27_Intelligent_Ranking_Engine.md.
"""

from __future__ import annotations


class RankingException(Exception):
    """Base class for every exception this package raises."""


class RankingConfigurationError(RankingException):
    """A ranking rule/profile is misconfigured or can't be resolved — an unknown
    `rule_key`, `register_ranking_rule` given something that isn't a `RankingRule`,
    or a `RankingWeights` given a negative weight.
    """


class RankingEvaluationError(RankingException):
    """A rule was resolved but its own `evaluate()` raised — the ranking equivalent
    of `GeoCalculationError`/`FilterValidationError`: caught by the pipeline so one
    broken rule can't take down the entire ranking run, recorded as a warning on the
    affected apartment instead of propagating as a bare exception.
    """
