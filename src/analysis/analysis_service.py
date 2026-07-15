"""The Deep Analysis Engine's persistence and read-side orchestration. Functions, not
a class — same reasoning as `history_service.py`/`search_memory_service.py`/
`knowledge_service.py`: no state beyond the `conn` every call already takes.

Write side: `record_analysis` persists one `AnalysisResult` — one
`apartment_analysis_metrics` row per analyzer result *and* per composite score, but
only when there's an actual score to store (`metric_value` is `NOT NULL`; "no evidence"
results are never written — see docs/19_Analysis_Engine.md "Analysis History").

Read side: `latest_analysis`/`analysis_history` reconstruct `AnalysisResult`-shaped data
from stored metrics — with one honest limitation: a persisted metric has no `warnings`
for the case where an analyzer had no evidence (that case was never written), so
reconstructed history can show *what was scored*, never *why something wasn't*. Only
the in-memory `AnalysisResult` returned directly by `AnalysisEngine.analyze()` (the
same run) can show the full warnings — see `core/agent.py`'s integration.
"""

from __future__ import annotations

import sqlite3

from src.analysis.models import AnalysisResult, AnalyzerResult, CompositeScore
from src.storage import analysis_metrics_repository
from src.storage.models import ApartmentAnalysisMetric

_COMPOSITE_PREFIX = "composite:"


def record_analysis(conn: sqlite3.Connection, result: AnalysisResult) -> None:
    for analyzer_result in result.analyzer_results:
        if analyzer_result.score is None:
            continue  # no evidence — nothing to persist, see module docstring
        analysis_metrics_repository.add_metric(
            conn,
            ApartmentAnalysisMetric(
                apartment_id=result.apartment_id,
                metric_name=analyzer_result.analyzer_name,
                metric_value=analyzer_result.score,
                source_module=analyzer_result.source,
                computed_at=analyzer_result.computed_at,
                search_id=result.search_id,
                confidence=analyzer_result.confidence,
                evidence=analyzer_result.evidence,
                warnings=analyzer_result.warnings,
                analyzer_version=analyzer_result.version,
            ),
        )

    for composite in result.composite_scores:
        if composite.score is None:
            continue
        analysis_metrics_repository.add_metric(
            conn,
            ApartmentAnalysisMetric(
                apartment_id=result.apartment_id,
                metric_name=f"{_COMPOSITE_PREFIX}{composite.name}",
                metric_value=composite.score,
                source_module="src.analysis.scoring",
                computed_at=result.computed_at,
                search_id=result.search_id,
                evidence=[f"Computed from: {', '.join(composite.component_analyzer_names)}"],
            ),
        )


def latest_analysis(conn: sqlite3.Connection, apartment_id: str) -> AnalysisResult | None:
    metrics = analysis_metrics_repository.get_latest_metrics_for_apartment(conn, apartment_id)
    if not metrics:
        return None
    return _metrics_to_analysis_result(apartment_id, metrics)


def analysis_history(conn: sqlite3.Connection, apartment_id: str) -> list[AnalysisResult]:
    """Every past analysis run for this apartment, oldest first — reconstructed by
    grouping stored metrics on their shared `computed_at` (see `AnalysisContext`).
    """
    metrics = analysis_metrics_repository.get_metrics_for_apartment(conn, apartment_id)
    by_computed_at: dict = {}
    for metric in metrics:
        by_computed_at.setdefault(metric.computed_at, []).append(metric)

    return [
        _metrics_to_analysis_result(apartment_id, group)
        for _, group in sorted(by_computed_at.items(), key=lambda pair: pair[0])
    ]


def _metrics_to_analysis_result(apartment_id: str, metrics: list[ApartmentAnalysisMetric]) -> AnalysisResult:
    analyzer_results = []
    composite_scores = []
    search_id = None
    computed_at = metrics[0].computed_at

    for metric in metrics:
        search_id = search_id or metric.search_id
        if metric.metric_name.startswith(_COMPOSITE_PREFIX):
            composite_scores.append(
                CompositeScore(
                    name=metric.metric_name[len(_COMPOSITE_PREFIX):],
                    score=metric.metric_value,
                    component_analyzer_names=[],
                )
            )
        else:
            analyzer_results.append(
                AnalyzerResult(
                    analyzer_name=metric.metric_name,
                    apartment_id=apartment_id,
                    score=metric.metric_value,
                    confidence=metric.confidence,
                    evidence=metric.evidence or [],
                    warnings=metric.warnings or [],
                    computed_at=metric.computed_at,
                    version=metric.analyzer_version or "unknown",
                    source=metric.source_module,
                )
            )

    return AnalysisResult(
        apartment_id=apartment_id,
        search_id=search_id,
        computed_at=computed_at,
        analyzer_results=analyzer_results,
        composite_scores=composite_scores,
    )
