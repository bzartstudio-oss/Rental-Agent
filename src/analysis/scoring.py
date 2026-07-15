"""Composite scoring — see docs/19_Analysis_Engine.md "Scoring Model".

The computation (`compute_composite_scores`) is generic: a weighted average over
whichever component analyzers actually produced a score, using confidence as the
weight multiplier. The composition itself — which analyzers feed which composite, and
how much each contributes — is *data* (`CompositeScoreDefinition`/`ScoringConfiguration`),
not hardcoded into the function, per the mission's explicit "do not hardcode weights."
`default_scoring_configuration()` supplies a reasonable starting point; any caller can
build and pass its own `ScoringConfiguration` instead (`AnalysisEngine.__init__` takes
one), the same "generic logic + swappable config object" shape as
`ranking/scoring.py`'s weighted-sum over `search/criteria.py`'s registered filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.models import AnalyzerResult, CompositeScore


@dataclass(frozen=True)
class CompositeScoreDefinition:
    name: str
    weights: dict[str, float]  # analyzer_name -> weight, e.g. {"walking_distance": 1.0}


@dataclass
class ScoringConfiguration:
    composites: list[CompositeScoreDefinition] = field(default_factory=list)
    overall_weights: dict[str, float] = field(default_factory=dict)  # composite name -> weight


def default_scoring_configuration() -> ScoringConfiguration:
    """A reasonable default composition — not the only valid one. Every weight here is
    ordinary configuration data; changing what feeds "Convenience Score" or how much
    Walking Distance matters to "Accessibility Score" means editing this function (or
    passing a different `ScoringConfiguration` to `AnalysisEngine`), never touching
    `compute_composite_scores`, an analyzer, or `AnalysisPipeline`.
    """
    location = CompositeScoreDefinition(
        name="location_score",
        weights={"walking_distance": 0.5, "public_transport": 0.3, "nearby_parks": 0.2},
    )
    convenience = CompositeScoreDefinition(
        name="convenience_score",
        weights={
            "nearby_supermarkets": 0.35,
            "nearby_pharmacies": 0.25,
            "nearby_restaurants": 0.25,
            "nearby_parking": 0.15,
        },
    )
    lifestyle = CompositeScoreDefinition(
        name="lifestyle_score",
        weights={"nearby_restaurants": 0.4, "nearby_gyms": 0.35, "nearby_parks": 0.25},
    )
    accessibility = CompositeScoreDefinition(
        name="accessibility_score",
        weights={
            "walking_distance": 0.25,
            "public_transport": 0.25,
            "nearby_parking": 0.2,
            "nearby_hospitals": 0.15,
            "nearby_schools": 0.1,
            "nearby_universities": 0.05,
        },
    )
    return ScoringConfiguration(
        composites=[location, convenience, lifestyle, accessibility],
        overall_weights={
            "location_score": 0.3,
            "convenience_score": 0.25,
            "lifestyle_score": 0.2,
            "accessibility_score": 0.25,
        },
    )


def compute_composite_scores(
    analyzer_results: list[AnalyzerResult], config: ScoringConfiguration
) -> list[CompositeScore]:
    """Builds every named composite from `config`, then a final "Overall Analysis
    Score" as a weighted average over those composites (`config.overall_weights`).
    `score=None` for a composite whose components all lack evidence — never a
    fabricated `0.0` (see `AnalyzerResult`'s docstring for why that convention matters).
    """
    results_by_name = {result.analyzer_name: result for result in analyzer_results}

    composites = [
        CompositeScore(
            name=definition.name,
            score=_weighted_average(results_by_name, definition.weights),
            component_analyzer_names=list(definition.weights),
        )
        for definition in config.composites
    ]

    overall_inputs = {composite.name: composite.score for composite in composites}
    overall_score = _weighted_average_of_scores(overall_inputs, config.overall_weights)
    composites.append(
        CompositeScore(
            name="overall_analysis_score",
            score=overall_score,
            component_analyzer_names=list(config.overall_weights),
        )
    )
    return composites


def _weighted_average(results_by_name: dict[str, AnalyzerResult], weights: dict[str, float]) -> float | None:
    total_weight = 0.0
    weighted_sum = 0.0
    for analyzer_name, weight in weights.items():
        result = results_by_name.get(analyzer_name)
        if result is None or result.score is None:
            continue
        confidence = result.confidence if result.confidence is not None else 1.0
        effective_weight = weight * confidence
        weighted_sum += result.score * effective_weight
        total_weight += effective_weight

    if total_weight == 0:
        return None
    return weighted_sum / total_weight


def _weighted_average_of_scores(scores: dict[str, float | None], weights: dict[str, float]) -> float | None:
    total_weight = 0.0
    weighted_sum = 0.0
    for name, weight in weights.items():
        score = scores.get(name)
        if score is None:
            continue
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return None
    return weighted_sum / total_weight
