"""`BaseAnalyzer` — every analysis module's common ancestor. See
docs/19_Analysis_Engine.md "Analyzer Lifecycle".

Deliberately a thin contract, not a template method like `BaseConnector` (v2.0 Step 5):
an analyzer's whole job is one pure-ish computation (`analyze()`), not a multi-stage
fetch/parse/validate sequence — there's no shared sequencing to factor out, only a
shared *shape* for the result. What analyzers do share (persistence, composite scoring,
running every registered analyzer for an apartment) lives in `AnalysisPipeline`/
`AnalysisEngine`/`analysis_service.py` instead, one level up.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.analysis.models import AnalysisContext, AnalyzerMetadata, AnalyzerResult
from src.storage.models import Apartment


class BaseAnalyzer(ABC):
    """`analyzer_name` is a required class attribute (e.g.
    `analyzer_name = "walking_distance"`) — both this analyzer's identity (the
    `metric_name` it writes to `apartment_analysis_metrics`) and its
    `AnalysisRegistry` key, read at `@register_analyzer` decoration time.
    """

    analyzer_name: str

    @abstractmethod
    def metadata(self) -> AnalyzerMetadata:
        """This analyzer's static self-description — one instance per analyzer class,
        not per apartment.
        """
        raise NotImplementedError

    @abstractmethod
    def analyze(self, apartment: Apartment, context: AnalysisContext) -> AnalyzerResult:
        """Compute this analyzer's result for one apartment. Should not raise for
        "no evidence available" — return a result with `score=None`/`confidence=None`
        and an explanatory `warnings` entry instead (see `AnalyzerResult`'s docstring),
        so a genuine exception here always means "this analyzer is actually broken,"
        never "this apartment happened to lack data." `AnalysisPipeline` isolates a
        broken analyzer the same way `core/agent.py` isolates a broken connector — one
        analyzer raising doesn't stop the rest from running or crash the search.
        """
        raise NotImplementedError
