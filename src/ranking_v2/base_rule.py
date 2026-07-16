"""`RankingRule` — the plugin contract every ranking factor implements, and
`RankingContext` — everything a rule may read beyond the apartment itself. See
docs/27_Intelligent_Ranking_Engine.md "Architecture"/"Rules".

`RankingContext` is deliberately the widest context object in this codebase so far —
it carries one optional field per INPUT the mission names (Dynamic Filters,
Geographic Intelligence, Analysis Results, Provider Health, Search History), plus
`conn`/`location` for the two inputs (Platform Reliability, Connector Reliability,
Price via Knowledge Engine's city average) that are always directly queryable given
a connection, needing no extra field. Every field defaults to `None` — a rule whose
needed field is absent degrades to an honest "no evidence" `RankingEvidence`, never
a fabricated score, mirroring `FilterContext`/`AnalysisContext`/`GeoContext`'s same
reasoning applied to a much larger set of simultaneous inputs.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from src.ranking_v2.metadata import RankingRuleMetadata
from src.ranking_v2.models import RankingEvidence
from src.storage.models import Apartment


@dataclass
class RankingContext:
    conn: sqlite3.Connection | None = None
    location: str | None = None
    computed_at: datetime | None = None

    # Dynamic Filters — soft/preference filter results (distinct from the hard
    # constraints already applied before ranking ever runs), keyed by apartment id.
    filter_results: dict = field(default_factory=dict)

    # Geographic Intelligence — this run's own GeoEnrichment per apartment.
    geo_enrichments: dict = field(default_factory=dict)

    # Analysis Results — this run's own AnalysisResult per apartment.
    analysis_results: dict = field(default_factory=dict)

    # Provider Health — a live health snapshot per platform_id, taken once per run
    # (not per apartment) since a platform's provider health doesn't vary by listing.
    provider_health: dict = field(default_factory=dict)

    # Search History — one whole-run comparison against the previous search for this
    # location, if the caller computed one (src.search_memory.models.SearchComparison).
    search_comparison: object | None = None


class RankingRule(ABC):
    rule_key: str

    @abstractmethod
    def evaluate(self, apartment: Apartment, context: RankingContext) -> RankingEvidence:
        """Returns this rule's verdict on `apartment` — `raw_score`/`confidence`
        honestly `None` when the evidence this rule needs doesn't exist, never a
        guessed value. Never raises for missing *data*; only
        `RankingEvaluationError` (a genuine bug, e.g. malformed context) should ever
        propagate.
        """
        raise NotImplementedError

    @abstractmethod
    def metadata(self) -> RankingRuleMetadata:
        raise NotImplementedError
