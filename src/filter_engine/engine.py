"""`FilterEngine` — the pipeline: validation → normalization → execution → statistics
→ results. See docs/25_Dynamic_Filter_Engine.md "Filter Pipeline".

Two entry points, sharing one execution core: `run()` takes a flat criteria dict
(today's `SearchRequest.criteria` shape — implicitly an AND of every key, exactly
matching `search.criteria.apply_filters()`'s existing behavior) and `run_group()`
takes an explicit `FilterGroup` for AND/OR/NOT/nested composition. Neither
constructs a connector, touches the database for apartment data, or knows anything
about ranking — this class's only job is turning (apartments, criteria) into
(`FilterResult`s), same single responsibility every other v2.0/v2.5 engine keeps.
"""

from __future__ import annotations

import time
from typing import Any

from src.filter_engine.base_filter import FilterContext
from src.filter_engine.composition import FilterGroup, build_group_from_criteria, evaluate
from src.filter_engine.configuration import FilterConfiguration
from src.filter_engine.result import FilterResult
from src.filter_engine.statistics import FilterStatistics, compute_filter_statistics
from src.filter_engine.validator import FilterValidator
from src.search.criteria import extract_value
from src.storage.models import Apartment


class FilterEngine:
    def __init__(self, config: FilterConfiguration | None = None) -> None:
        self.config = config or FilterConfiguration()

    def run(
        self,
        apartments: list[Apartment],
        criteria: dict[str, Any],
        context: FilterContext | None = None,
    ) -> tuple[list[FilterResult], FilterStatistics]:
        """The flat-dict entry point — every key in `criteria` must match (implicit
        AND), exactly reproducing `search.criteria.apply_filters()`'s existing
        contract. Values may be a bare value or the existing `{"value": ..., "weight":
        ...}` wrapper (`extract_value()` unwraps either, same as today).

        A criterion naming a *disabled* filter is intentionally left for the
        validation stage (inside `run_group()`) to reject, not silently dropped here
        — a request for a filter the current `FilterConfiguration` has turned off is
        a real mismatch worth failing loudly on, the same "fail fast" reasoning
        `FilterValidator` already applies to an unregistered key.
        """
        normalized = {key: extract_value(raw) for key, raw in criteria.items()}
        group = build_group_from_criteria(normalized)
        return self.run_group(apartments, group, context)

    def run_group(
        self,
        apartments: list[Apartment],
        group: FilterGroup,
        context: FilterContext | None = None,
    ) -> tuple[list[FilterResult], FilterStatistics]:
        """The composed entry point — an explicit `FilterGroup` tree for AND/OR/NOT/
        nesting. `run()` is a thin wrapper around this for the common flat-AND case.
        """
        context = context or FilterContext()
        started = time.perf_counter()

        # Validation stage — delegated to FilterValidator (the one, canonical
        # validation implementation both entry points share), before any apartment
        # is touched, so a bad request fails immediately.
        FilterValidator.validate_group_strict(group, self.config)

        # Execution stage — apartments in the given order, each apartment's tree
        # walked in the same fixed order every time (Python lists/dataclass fields
        # preserve insertion order) — deterministic by construction, not by an added
        # sorting step.
        results = []
        for apartment in apartments:
            matches, per_filter = evaluate(group, apartment, context)
            results.append(FilterResult(apartment_id=apartment.id, matches=matches, per_filter=per_filter))

        execution_time_ms = int((time.perf_counter() - started) * 1000)

        # Statistics stage — computed from the results just produced, not folded into
        # the execution loop itself (single responsibility; see statistics.py).
        statistics = compute_filter_statistics(results, execution_time_ms=execution_time_ms)

        return results, statistics

    def filter_apartments(
        self,
        apartments: list[Apartment],
        criteria: dict[str, Any],
        context: FilterContext | None = None,
    ) -> list[Apartment]:
        """The common case: just the apartments that matched, in their original
        order — what `ranking/ranking_engine.py` actually needs, mirroring
        `search.criteria.apply_filters()`'s own return shape so it's a drop-in
        replacement wherever that's used.
        """
        results, _ = self.run(apartments, criteria, context)
        matched_ids = {result.apartment_id for result in results if result.matches}
        return [apartment for apartment in apartments if apartment.id in matched_ids]
