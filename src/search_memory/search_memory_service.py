"""Search Memory's write- and read-side orchestration (v2.0 Step 3 mission). Functions,
not a class — same reasoning as src/history/history_service.py: no state beyond the
`conn` every call already takes.

Write side: `record_completed_search` is called once by `RentalResearchAgent.run()`
after ranking + report generation ("the Research Agent must automatically create a
Search Execution record after every completed search"). It finds the previous search
for the same location (docs/17_Search_Memory.md "Run-Over-Run Comparison"), computes
new/removed/changed apartment counts against it, persists every run stat via one
`UPDATE`, and returns the full comparison (or `None` if this is the first search ever
made for this location).

Read side: `latest_search`/`search_history`/`search_timeline`/`compare_searches`/
`average_execution_time`/`average_apartment_count`/`search_statistics` — the methods
named in the mission's "EXPOSE METHODS" section, translated to this project's
snake_case convention.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from statistics import mean

from src.history import history_service
from src.search_memory import comparison
from src.search_memory.models import (
    ApartmentAvailabilityChange,
    ApartmentPriceChange,
    SearchComparison,
    SearchExecution,
    SearchStatistics,
    SearchTimeline,
)
from src.storage import apartment_history_repository, search_memory_repository, search_repository
from src.storage.models import SearchRequestRecord


def record_completed_search(
    conn: sqlite3.Connection,
    request,
    *,
    execution_time_ms: int,
    discovered_platform_ids: list[str],
    searched_platform_ids: list[str],
    connector_versions: dict[str, str | None],
    errors: list[str],
    apartment_count: int,
    report_path: str,
) -> SearchComparison | None:
    """`request` is a `search.search_request.SearchRequest` (not imported here to avoid
    a needless import — only `.id`, `.location`, and `.created_at` are used, all of
    which `storage.models.SearchRequestRecord` also has, so this function would work
    unchanged against either).
    """
    current_ids = search_memory_repository.get_observed_apartment_ids(conn, request.id)
    previous_record = search_memory_repository.find_previous_search(
        conn, request.location, before_created_at=request.created_at, exclude_search_id=request.id
    )

    comparison_result = None
    if previous_record is None:
        new_ids, removed_ids = sorted(current_ids), []
        changed_ids, price_changes, availability_changes = [], [], []
    else:
        previous_ids = search_memory_repository.get_observed_apartment_ids(conn, previous_record.id)
        new_ids, removed_ids = comparison.diff_apartment_sets(previous_ids, current_ids)
        intersecting_ids = sorted(previous_ids & current_ids)
        changed_ids, price_changes, availability_changes = _compare_intersecting_apartments(
            conn, intersecting_ids, previous_record.id, previous_record.created_at, request.id, request.created_at
        )

    failed_platform_ids = sorted(set(discovered_platform_ids) - set(searched_platform_ids))
    runtime_stats = {
        "failed_platform_ids": failed_platform_ids,
        "warnings": [],
        "errors": errors,
        "connector_versions": connector_versions,
        "pdf_report_path": None,
    }

    search_memory_repository.complete_search_execution(
        conn,
        request.id,
        execution_time_ms=execution_time_ms,
        discovered_platform_ids=discovered_platform_ids,
        searched_platform_ids=searched_platform_ids,
        apartment_count=apartment_count,
        new_apartment_count=len(new_ids),
        removed_apartment_count=len(removed_ids),
        changed_apartment_count=len(changed_ids),
        report_path=report_path,
        runtime_stats=runtime_stats,
    )

    if previous_record is None:
        return None

    previous_searched = previous_record.searched_platform_ids or []
    current_quality = comparison.search_quality(apartment_count, len(searched_platform_ids))
    previous_quality = comparison.search_quality(previous_record.apartment_count, len(previous_searched))

    return SearchComparison(
        previous_search_id=previous_record.id,
        current_search_id=request.id,
        new_apartment_ids=new_ids,
        removed_apartment_ids=removed_ids,
        changed_apartment_ids=changed_ids,
        price_changes=price_changes,
        availability_changes=availability_changes,
        connector_failures=failed_platform_ids,
        platform_coverage_change=comparison.platform_coverage_change(previous_searched, searched_platform_ids),
        execution_time_delta_ms=(
            execution_time_ms - previous_record.execution_time_ms
            if previous_record.execution_time_ms is not None
            else None
        ),
        search_quality_delta=(
            current_quality - previous_quality if current_quality is not None and previous_quality is not None else None
        ),
    )


def latest_search(conn: sqlite3.Connection, location: str | None = None) -> SearchExecution | None:
    records = search_memory_repository.get_search_history(conn, location=location, limit=1)
    return _to_search_execution(records[0]) if records else None


def search_history(
    conn: sqlite3.Connection, location: str | None = None, limit: int | None = None
) -> list[SearchExecution]:
    """Newest-first."""
    records = search_memory_repository.get_search_history(conn, location=location, limit=limit)
    return [_to_search_execution(record) for record in records]


def search_timeline(conn: sqlite3.Connection, location: str) -> SearchTimeline:
    """Oldest-first — see `SearchTimeline`'s docstring."""
    records = search_memory_repository.get_search_history(conn, location=location)
    records.reverse()
    return SearchTimeline(location=location, executions=[_to_search_execution(record) for record in records])


def compare_searches(conn: sqlite3.Connection, search_id_a: str, search_id_b: str) -> SearchComparison:
    """`CompareSearch(search_a, search_b)` — order doesn't need to match creation order;
    whichever of the two was created first is treated as "previous."
    """
    record_a = search_repository.get_search_request(conn, search_id_a)
    record_b = search_repository.get_search_request(conn, search_id_b)
    if record_a is None or record_b is None:
        raise ValueError("Both search ids must refer to existing search_requests rows")

    previous, current = (
        (record_a, record_b) if record_a.created_at <= record_b.created_at else (record_b, record_a)
    )
    return _build_comparison(conn, previous, current)


def average_execution_time(conn: sqlite3.Connection, location: str | None = None) -> float | None:
    return search_statistics(conn, location).average_execution_time_ms


def average_apartment_count(conn: sqlite3.Connection, location: str | None = None) -> float | None:
    return search_statistics(conn, location).average_apartment_count


def search_statistics(conn: sqlite3.Connection, location: str | None = None) -> SearchStatistics:
    records = search_memory_repository.get_search_history(conn, location=location)

    def _average(attr: str) -> float | None:
        values = [getattr(record, attr) for record in records if getattr(record, attr) is not None]
        return mean(values) if values else None

    return SearchStatistics(
        location=location,
        search_count=len(records),
        average_execution_time_ms=_average("execution_time_ms"),
        average_apartment_count=_average("apartment_count"),
        average_new_apartment_count=_average("new_apartment_count"),
        average_removed_apartment_count=_average("removed_apartment_count"),
        average_changed_apartment_count=_average("changed_apartment_count"),
    )


def _build_comparison(
    conn: sqlite3.Connection, previous_record: SearchRequestRecord, current_record: SearchRequestRecord
) -> SearchComparison:
    previous_ids = search_memory_repository.get_observed_apartment_ids(conn, previous_record.id)
    current_ids = search_memory_repository.get_observed_apartment_ids(conn, current_record.id)
    new_ids, removed_ids = comparison.diff_apartment_sets(previous_ids, current_ids)
    intersecting_ids = sorted(previous_ids & current_ids)
    changed_ids, price_changes, availability_changes = _compare_intersecting_apartments(
        conn, intersecting_ids, previous_record.id, previous_record.created_at, current_record.id, current_record.created_at
    )

    current_searched = current_record.searched_platform_ids or []
    previous_searched = previous_record.searched_platform_ids or []
    current_discovered = current_record.discovered_platform_ids or []

    current_quality = comparison.search_quality(current_record.apartment_count, len(current_searched))
    previous_quality = comparison.search_quality(previous_record.apartment_count, len(previous_searched))

    return SearchComparison(
        previous_search_id=previous_record.id,
        current_search_id=current_record.id,
        new_apartment_ids=new_ids,
        removed_apartment_ids=removed_ids,
        changed_apartment_ids=changed_ids,
        price_changes=price_changes,
        availability_changes=availability_changes,
        connector_failures=sorted(set(current_discovered) - set(current_searched)),
        platform_coverage_change=comparison.platform_coverage_change(previous_searched, current_searched),
        execution_time_delta_ms=(
            current_record.execution_time_ms - previous_record.execution_time_ms
            if current_record.execution_time_ms is not None and previous_record.execution_time_ms is not None
            else None
        ),
        search_quality_delta=(
            current_quality - previous_quality if current_quality is not None and previous_quality is not None else None
        ),
    )


def _compare_intersecting_apartments(
    conn: sqlite3.Connection,
    apartment_ids: list[str],
    previous_search_id: str,
    previous_created_at: datetime,
    current_search_id: str,
    current_created_at: datetime,
) -> tuple[list[str], list[ApartmentPriceChange], list[ApartmentAvailabilityChange]]:
    """For every apartment observed in *both* searches, reconstructs its price/status/
    title/description as of each search and checks for an image add/remove tagged with
    the current search — docs/17_Search_Memory.md's "at least one history row" test,
    reimplemented via `_value_as_of` (see its docstring for why a raw timestamp window
    doesn't work) rather than a naive scan.
    """
    changed_ids = []
    price_changes = []
    availability_changes = []

    for apartment_id in apartment_ids:
        price_timeline = history_service.price_timeline(conn, apartment_id)
        old_price = _value_as_of(price_timeline, previous_search_id, previous_created_at, "price")
        new_price = _value_as_of(price_timeline, current_search_id, current_created_at, "price")
        price_changed = old_price != new_price
        if price_changed:
            price_changes.append(ApartmentPriceChange(apartment_id=apartment_id, old_price=old_price, new_price=new_price))

        availability_timeline = history_service.availability_timeline(conn, apartment_id)
        old_status = _value_as_of(availability_timeline, previous_search_id, previous_created_at, "status")
        new_status = _value_as_of(availability_timeline, current_search_id, current_created_at, "status")
        availability_changed = old_status != new_status
        if availability_changed:
            availability_changes.append(
                ApartmentAvailabilityChange(apartment_id=apartment_id, old_status=old_status, new_status=new_status)
            )

        change_log = apartment_history_repository.get_change_log(conn, apartment_id)
        title_entries = [entry for entry in change_log if entry.field_name == "title"]
        old_title = _value_as_of(title_entries, previous_search_id, previous_created_at, "new_value")
        new_title = _value_as_of(title_entries, current_search_id, current_created_at, "new_value")

        description_entries = [entry for entry in change_log if entry.field_name == "description"]
        old_description = _value_as_of(description_entries, previous_search_id, previous_created_at, "new_value")
        new_description = _value_as_of(description_entries, current_search_id, current_created_at, "new_value")

        image_events = apartment_history_repository.get_image_events(conn, apartment_id)
        images_changed_this_search = any(event.search_id == current_search_id for event in image_events)

        if (
            price_changed
            or availability_changed
            or old_title != new_title
            or old_description != new_description
            or images_changed_this_search
        ):
            changed_ids.append(apartment_id)

    return changed_ids, price_changes, availability_changes


def _value_as_of(entries: list, as_of_search_id: str, as_of_created_at: datetime, attr: str):
    """The value of `attr` "as of" a given search: the latest entry that either belongs
    to that search itself (`entry.search_id == as_of_search_id`) or was observed at or
    before that search started (`entry.observed_at <= as_of_created_at`, catching earlier
    searches and any history written outside a search context).

    A pure timestamp comparison isn't enough: a search's *own* writes happen strictly
    after `SearchRequest.created_at` is stamped (processing takes real wall-clock time —
    discovery, connector fetches, ranking, report generation all happen in between), so
    "observed_at > previous_search.created_at" is true even for rows *that search
    itself* wrote, which would wrongly count a brand-new apartment's very first price/
    title/image entry as a "change" relative to the search that created it. Matching on
    `search_id` first sidesteps that entirely — see learning/architecture_notes.md.

    v2.0 Step 4.5 note — why this doesn't share code with
    `src/history/history_service.py::previous_version` (deliberately not merged, see
    that function's docstring for the full writeup): this reconstructs a value as of
    one of two *specific, named* searches being compared, which may not be adjacent in
    the apartment's own history at all; `previous_version` reconstructs "whatever came
    right before the latest change," with no search identity involved, for a plain
    single-apartment read. Different parameters, different questions — merging them
    would mean either bolting an unused `search_id` parameter onto every
    `history_service` read call, or losing the identity-matching this function needs
    to stay correct.
    """
    applicable = [
        entry for entry in entries if entry.search_id == as_of_search_id or entry.observed_at <= as_of_created_at
    ]
    if not applicable:
        return None
    return getattr(max(applicable, key=lambda entry: entry.observed_at), attr)


def _to_search_execution(record: SearchRequestRecord) -> SearchExecution:
    criteria_payload = json.loads(record.criteria_json)
    runtime_stats = record.runtime_stats or {}
    return SearchExecution(
        id=record.id,
        location=criteria_payload.get("location", ""),
        criteria=criteria_payload.get("criteria", {}),
        created_at=record.created_at,
        label=record.label,
        execution_time_ms=record.execution_time_ms,
        discovered_platform_ids=record.discovered_platform_ids or [],
        searched_platform_ids=record.searched_platform_ids or [],
        failed_platform_ids=runtime_stats.get("failed_platform_ids", []),
        apartment_count=record.apartment_count,
        new_apartment_count=record.new_apartment_count,
        removed_apartment_count=record.removed_apartment_count,
        changed_apartment_count=record.changed_apartment_count,
        report_path=record.report_path,
        pdf_report_path=runtime_stats.get("pdf_report_path"),
        warnings=runtime_stats.get("warnings", []),
        errors=runtime_stats.get("errors", []),
        connector_versions=runtime_stats.get("connector_versions", {}),
        runtime_stats=runtime_stats,
    )
