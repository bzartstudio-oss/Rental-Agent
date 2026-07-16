"""`EventDetector` — the plugin contract every change-detection source
implements, and `MonitoringDetectionContext` — the shared read-only evidence
bundle every detector's `detect()` receives. Mirrors
`src.discovery.automatic.base_provider.DiscoveryProvider`'s exact shape:
`MonitoringEngine`/`MonitoringRegistry` require zero changes when a new
detector is added — "adding a new event type" (docs/30) is "add a string
constant plus one detector," never a change to the engine itself.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from src.monitoring.metadata import EventDetectorMetadata
from src.monitoring.models import MonitoringEvent, MonitoringPolicy, MonitoringRun, SavedSearch, SavedSearchVersion
from src.storage.models import SearchResultEntry


@dataclass
class MonitoringDetectionContext:
    """Every piece of already-computed evidence a detector might need — never a
    live `conn` query the detector has to know how to write itself beyond
    simple lookups, the same "context carries evidence, rule stays simple"
    shape `RankingContext`/`FilterContext`/`PreferenceContext` already use.
    """

    conn: sqlite3.Connection
    saved_search: SavedSearch
    version: SavedSearchVersion
    run: MonitoringRun
    policy: MonitoringPolicy
    now: datetime
    previous_run: MonitoringRun | None = None
    search_comparison: object | None = None  # search_memory.models.SearchComparison | None
    current_search_results: list[SearchResultEntry] = field(default_factory=list)
    previous_search_results: list[SearchResultEntry] = field(default_factory=list)
    discovery_comparison: object | None = None  # discovery.automatic.models.DiscoveryComparison | None
    current_observed_apartment_ids: set[str] = field(default_factory=set)
    prior_observed_apartment_sets: list[set[str]] = field(default_factory=list)  # newest-first, excludes this run


class EventDetector(ABC):
    detector_id: str

    @abstractmethod
    def metadata(self) -> EventDetectorMetadata:
        raise NotImplementedError

    @abstractmethod
    def detect(self, context: MonitoringDetectionContext) -> list[MonitoringEvent]:
        """Returns every event this detector found — an empty list is an
        honest "nothing changed," never fabricated. Must not raise for an
        ordinary "no evidence" case; only a genuine bug should propagate.
        """
        raise NotImplementedError
