"""`AnalysisEngine` — the Deep Analysis Engine's entry point, what `core/agent.py`
actually holds and calls. See docs/19_Analysis_Engine.md "Architecture".

Runs `AnalysisPipeline` once per apartment across a whole search's results. Does not
persist anything itself — `core/agent.py` passes the returned `AnalysisResult`s to
`src.analysis.analysis_service.record_analysis()` separately, the same
compute-then-persist split every other v2.0 engine/service pair already uses
(`history_service`, `search_memory_service`, `knowledge_service`).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.analysis.models import AnalysisContext, AnalysisResult
from src.analysis.pipeline import AnalysisPipeline
from src.analysis.scoring import ScoringConfiguration
from src.storage.models import Apartment


class AnalysisEngine:
    def __init__(self, scoring_config: ScoringConfiguration | None = None) -> None:
        self._pipeline = AnalysisPipeline(scoring_config)

    def analyze(
        self,
        conn: sqlite3.Connection,
        apartments: list[Apartment],
        *,
        location: str,
        search_id: str | None = None,
    ) -> dict[str, AnalysisResult]:
        """Analyzes every apartment in `apartments`, returning a dict keyed by
        `apartment_id`. Every apartment in this call shares one `computed_at` — see
        `AnalysisContext`'s docstring for why that consistency matters for history
        reconstruction.
        """
        computed_at = datetime.now(timezone.utc)
        context = AnalysisContext(conn=conn, location=location, computed_at=computed_at, search_id=search_id)

        results: dict[str, AnalysisResult] = {}
        for apartment in apartments:
            analyzer_results, composite_scores = self._pipeline.run(apartment, context)
            results[apartment.id] = AnalysisResult(
                apartment_id=apartment.id,
                search_id=search_id,
                computed_at=computed_at,
                analyzer_results=analyzer_results,
                composite_scores=composite_scores,
            )
        return results
