"""Domain shapes for the Deep Analysis Engine — see docs/19_Analysis_Engine.md.

`AnalyzerResult` is what every individual analyzer produces; `AnalysisResult` is one
apartment's complete analysis (every analyzer's result plus composite scores) for one
run. Neither is a database row — `storage.models.ApartmentAnalysisMetric` (via
`storage/analysis_metrics_repository.py`) is the persisted shape; `analysis_service.py`
converts between the two.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AnalysisContext:
    """Everything an analyzer needs beyond the `Apartment` itself. `computed_at` is set
    once per analysis *run* (not per analyzer) — every analyzer and composite score in
    the same run shares the exact same timestamp, which is what lets
    `storage.analysis_metrics_repository.get_latest_metrics_for_apartment` reconstruct
    "everything computed in the most recent run" by grouping on that one value.

    `location` is the same free-text string Search Memory/Knowledge Engine already key
    curated/aggregated data on (docs/17_Search_Memory.md, docs/16_Knowledge_Engine.md) —
    kept consistent rather than inventing a fourth location-keying convention.
    """

    conn: sqlite3.Connection
    location: str
    computed_at: datetime
    search_id: str | None = None


@dataclass
class AnalyzerMetadata:
    """An analyzer's static self-description — mirrors `ConnectorMetadata`
    (v2.0 Step 5) deliberately: both answer "what is this plugin, and what can it do"
    for a registry-discovered component.
    """

    analyzer_name: str
    version: str
    category: str  # e.g. "proximity", "transport", "amenity"
    description: str
    required_evidence: list[str] = field(default_factory=list)


@dataclass
class AnalyzerResult:
    """One analyzer's output for one apartment, in one run. `score`/`confidence` are
    both `None` together — "no evidence yet," never a fabricated `0.0` (the same
    nullable-means-no-evidence convention as every rollup elsewhere in this system,
    docs/03_Data_Model.md). Not persisted at all when `score is None` — see
    `analysis_service.py`; the in-memory result (this object) is still what the report
    uses to show *why* (via `warnings`).
    """

    analyzer_name: str
    apartment_id: str
    score: float | None
    confidence: float | None
    evidence: list[str]
    warnings: list[str]
    computed_at: datetime
    version: str
    source: str


@dataclass
class CompositeScore:
    """One weighted-average score over a named set of component analyzers — see
    `scoring.py`. `score=None` when none of its components had evidence.
    """

    name: str
    score: float | None
    component_analyzer_names: list[str]


@dataclass
class AnalysisResult:
    """One apartment's complete analysis for one run — every registered analyzer's
    result plus every composite score. This, not a database row, is what
    `core/agent.py` passes to the Report Generator directly (in-memory, same run) —
    see docs/19_Analysis_Engine.md "Report Integration" for why persisted history
    alone isn't enough to show a "no evidence" warning in a report.
    """

    apartment_id: str
    search_id: str | None
    computed_at: datetime
    analyzer_results: list[AnalyzerResult]
    composite_scores: list[CompositeScore]

    def analyzer_result(self, analyzer_name: str) -> AnalyzerResult | None:
        return next((r for r in self.analyzer_results if r.analyzer_name == analyzer_name), None)

    def composite_score(self, name: str) -> CompositeScore | None:
        return next((c for c in self.composite_scores if c.name == name), None)
