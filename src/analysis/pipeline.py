"""`AnalysisPipeline` — runs every registered analyzer against one apartment and
computes composite scores. See docs/19_Analysis_Engine.md "Pipeline".

One level below `AnalysisEngine` (which runs this pipeline across every apartment in a
search); one level above `BaseAnalyzer` (which this pipeline calls, one instance per
registered analyzer class). Analyzer modules are imported here — not by
`AnalysisEngine` — because importing `src.analysis.analyzers` is what triggers every
built-in analyzer's `@register_analyzer` decorator; anything that constructs a
`AnalysisPipeline` gets a fully-populated `AnalysisRegistry` for free.
"""

from __future__ import annotations

from src.analysis import analyzers as _analyzers  # noqa: F401 - import triggers registration
from src.analysis.models import AnalysisContext, AnalyzerResult
from src.analysis.registry import AnalysisRegistry
from src.analysis.scoring import ScoringConfiguration, compute_composite_scores, default_scoring_configuration
from src.storage.models import Apartment


class AnalysisPipeline:
    def __init__(self, scoring_config: ScoringConfiguration | None = None) -> None:
        self._scoring_config = scoring_config or default_scoring_configuration()

    def run(self, apartment: Apartment, context: AnalysisContext) -> tuple[list[AnalyzerResult], list]:
        """Runs every registered analyzer for `apartment`, then computes composite
        scores from whichever analyzers produced real evidence. A single analyzer
        raising is isolated (converted into a `score=None` result with a warning) —
        it does not stop the rest of the analyzers from running, matching how a broken
        connector doesn't stop the rest of a search (`core/agent.py`).
        """
        analyzer_results = [self._run_one(analyzer_class(), apartment, context) for analyzer_class in AnalysisRegistry.all()]
        composite_scores = compute_composite_scores(analyzer_results, self._scoring_config)
        return analyzer_results, composite_scores

    @staticmethod
    def _run_one(analyzer, apartment: Apartment, context: AnalysisContext) -> AnalyzerResult:
        try:
            return analyzer.analyze(apartment, context)
        except Exception as exc:
            try:
                version = analyzer.metadata().version
            except Exception:
                version = "unknown"
            return AnalyzerResult(
                analyzer_name=analyzer.analyzer_name,
                apartment_id=apartment.id,
                score=None,
                confidence=None,
                evidence=[],
                warnings=[f"Analyzer raised an unexpected error: {exc}"],
                computed_at=context.computed_at,
                version=version,
                source="analyzer_error",
            )
