"""The Apartment History Engine's write- and read-side orchestration (v2.0 Step 2
mission: "History service"). Functions, not a class — there's no state to hold beyond
the `conn` every call already takes, matching this project's existing repository-style
modules (e.g. `discovery/platform_registry.py`) rather than the stateful `*Agent`/
`*Engine` classes that own a `Database` across a whole run.

Write side: turns a normalized observation into `Change` objects (src/history/
comparison.py) and appends them to `apartment_change_log` — never overwrites, never
deletes (docs/00_Project_Vision.md Principle 3). Called automatically by
`analyzers/engine.py::process_listing` for every listing the Research Agent processes,
so "every apartment observation" really does get saved into history, per the mission.

Read side: reconstructs timelines and prior states from the append-only tables an
apartment's history is spread across (there is no single unified "apartment version"
table — see docs/03_Data_Model.md; different fields change independently, so a
"version" is a per-field reconstruction, not one snapshot row).
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime

from src.history import comparison
from src.history.models import Change, ChangeType
from src.storage import apartment_history_repository, apartment_repository
from src.storage.models import (
    Apartment,
    ApartmentAvailabilityHistoryEntry,
    ApartmentChangeLogEntry,
    ApartmentImageEvent,
    ApartmentPriceHistoryEntry,
)


def record_new_apartment(
    conn: sqlite3.Connection, apartment: Apartment, observed_at: datetime, search_id: str | None = None
) -> list[Change]:
    """The generic-field half of the "NO" branch of docs/07_Analysis_Engine.md's Write
    Sequence: initial `apartment_change_log` rows for title (always has a value) and
    description (only if the connector provided one), `old_value=NULL`. Price/
    availability history and images are handled by `analyzers/engine.py` directly (they
    have their own dedicated tables/download mechanics, not generic change-log rows).
    """
    changes = []

    title_change = comparison.compare_title(apartment.id, None, apartment.title, observed_at, search_id=search_id)
    if title_change:
        changes.append(title_change)

    if apartment.description:
        description_change = comparison.compare_description(
            apartment.id, None, apartment.description, observed_at, search_id=search_id
        )
        if description_change:
            changes.append(description_change)

    for change in changes:
        _write_change_log(conn, change)

    return changes


def record_reobservation(
    conn: sqlite3.Connection,
    existing: Apartment,
    fields: dict,
    observed_at: datetime,
    search_id: str | None = None,
) -> list[Change]:
    """The generic-field half of the "YES" branch: compares title/description against
    the current row and writes an `apartment_change_log` row only for whichever
    actually changed — mirrors the "only write on actual change" discipline
    price/status already use. Returns every itemized change plus a trailing
    "listing_updated" summary `Change` (not persisted — see
    `comparison.summarize_listing_updated`) when at least one field changed.
    """
    changes = []

    title_change = comparison.compare_title(
        existing.id, existing.title, fields["title"], observed_at, search_id=search_id
    )
    if title_change:
        changes.append(title_change)

    description_change = comparison.compare_description(
        existing.id, existing.description, fields.get("description"), observed_at, search_id=search_id
    )
    if description_change:
        changes.append(description_change)

    for change in changes:
        _write_change_log(conn, change)

    summary = comparison.summarize_listing_updated(existing.id, changes, observed_at, search_id=search_id)
    return changes + ([summary] if summary else [])


def _write_change_log(conn: sqlite3.Connection, change: Change) -> None:
    apartment_history_repository.add_change_log_entry(
        conn,
        apartment_id=change.apartment_id,
        field_name=change.field_name,
        old_value=change.old_value,
        new_value=change.new_value,
        observed_at=change.observed_at,
        search_id=change.search_id,
    )


def latest_version(conn: sqlite3.Connection, apartment_id: str) -> Apartment | None:
    """The current-state row *is* the latest version (Principle 1, docs/03_Data_Model.md
    — it's a rollup kept fresh on every observation) — this is a thin, named wrapper so
    callers of the History Engine have one discoverable API instead of needing to know
    to reach into `apartment_repository` directly.
    """
    return apartment_repository.get_apartment(conn, apartment_id)


def previous_version(conn: sqlite3.Connection, apartment_id: str) -> Apartment | None:
    """Reconstructs the apartment as it was immediately *before* its most recent
    recorded change, one field at a time: price/status come from the second-newest row
    in their own history tables (the newest row *is* the current value, so "previous"
    is the one before it); title/description come from the `old_value` of their most
    recent `apartment_change_log` entry, if any (that entry's old_value already *is*
    "what it was before the latest change" — no second-newest lookup needed, since
    change_log only ever gets a row when something actually changed).

    Returns `None` if the apartment has never been observed more than once — there is
    no "previous version" of something seen exactly once.
    """
    current = apartment_repository.get_apartment(conn, apartment_id)
    if current is None:
        return None

    price_history = apartment_repository.get_price_history(conn, apartment_id)
    availability_history = apartment_repository.get_availability_history(conn, apartment_id)
    change_log = apartment_history_repository.get_change_log(conn, apartment_id)

    has_prior_price = len(price_history) >= 2
    has_prior_status = len(availability_history) >= 2
    title_entries = [entry for entry in change_log if entry.field_name == "title"]
    description_entries = [entry for entry in change_log if entry.field_name == "description"]

    if not (has_prior_price or has_prior_status or title_entries or description_entries):
        return None

    previous = replace(current)
    if has_prior_price:
        previous.current_price = price_history[-2].price
    if has_prior_status:
        previous.current_status = availability_history[-2].status
    if title_entries:
        previous.title = title_entries[-1].old_value
    if description_entries:
        previous.description = description_entries[-1].old_value
    return previous


def price_timeline(conn: sqlite3.Connection, apartment_id: str) -> list[ApartmentPriceHistoryEntry]:
    return apartment_repository.get_price_history(conn, apartment_id)


def availability_timeline(
    conn: sqlite3.Connection, apartment_id: str
) -> list[ApartmentAvailabilityHistoryEntry]:
    return apartment_repository.get_availability_history(conn, apartment_id)


def change_timeline(conn: sqlite3.Connection, apartment_id: str) -> list[Change]:
    """Every recorded change to this apartment, across every tracked field, merged from
    `apartment_price_history` + `apartment_availability_history` + `apartment_change_log`
    + `apartment_image_events` into one time-ordered list of `Change` objects — there is
    no single table this could be a straight `SELECT` from, since each field's history
    lives in whichever dedicated or generic table fits it (docs/03_Data_Model.md).
    """
    changes: list[Change] = []

    for entry in apartment_repository.get_price_history(conn, apartment_id):
        changes.append(_price_entry_to_change(entry))

    for entry in apartment_repository.get_availability_history(conn, apartment_id):
        changes.append(_availability_entry_to_change(entry))

    for entry in apartment_history_repository.get_change_log(conn, apartment_id):
        changes.append(_change_log_entry_to_change(entry))

    for entry in apartment_history_repository.get_image_events(conn, apartment_id):
        changes.append(_image_event_to_change(entry))

    changes.sort(key=lambda change: change.observed_at)
    return changes


def _price_entry_to_change(entry: ApartmentPriceHistoryEntry) -> Change:
    return Change(
        apartment_id=entry.apartment_id,
        change_type=ChangeType.PRICE_CHANGED,
        field_name="price",
        old_value=None,
        new_value=str(entry.price),
        observed_at=entry.observed_at,
        search_id=entry.search_id,
    )


def _availability_entry_to_change(entry: ApartmentAvailabilityHistoryEntry) -> Change:
    return Change(
        apartment_id=entry.apartment_id,
        change_type=ChangeType.AVAILABILITY_CHANGED,
        field_name="status",
        old_value=None,
        new_value=entry.status,
        observed_at=entry.observed_at,
        search_id=entry.search_id,
    )


def _change_log_entry_to_change(entry: ApartmentChangeLogEntry) -> Change:
    change_type = {
        "title": ChangeType.TITLE_CHANGED,
        "description": ChangeType.DESCRIPTION_CHANGED,
        "coordinates": ChangeType.COORDINATES_CHANGED,
    }.get(entry.field_name, f"{entry.field_name}_changed")
    return Change(
        apartment_id=entry.apartment_id,
        change_type=change_type,
        field_name=entry.field_name,
        old_value=entry.old_value,
        new_value=entry.new_value,
        observed_at=entry.observed_at,
        search_id=entry.search_id,
    )


def _image_event_to_change(entry: ApartmentImageEvent) -> Change:
    is_added = entry.event == "added"
    return Change(
        apartment_id=entry.apartment_id,
        change_type=ChangeType.IMAGE_ADDED if is_added else ChangeType.IMAGE_REMOVED,
        field_name="image",
        old_value=None if is_added else entry.source_url,
        new_value=entry.source_url if is_added else None,
        observed_at=entry.observed_at,
        search_id=entry.search_id,
    )
