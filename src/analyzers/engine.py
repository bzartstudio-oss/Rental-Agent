"""Composes normalizer + deduplicator + change_detector + storage writes into the full
per-listing write sequence described in docs/07_Analysis_Engine.md "Write Sequence".

This is the Analysis Engine's *own* internal orchestration — distinct from core/agent.py,
which sequences *between* pipeline stages (Discovery, Connector, Analysis, Ranking,
Report) but must not contain any single stage's business logic
(docs/01_System_Architecture.md). Deciding insert-vs-update-with-history for one raw
listing, and whether to download its images, is squarely Analysis Engine business logic,
so it lives here, not in core/agent.py. (Not explicitly named in the original
docs/02_Folder_Guide.md package tree — added because normalizer/deduplicator/
change_detector need exactly one place that calls all three in the right order.)
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.analyzers import change_detector, normalizer
from src.analyzers.deduplicator import find_existing
from src.collectors import image_collector
from src.connectors.base import RawListing
from src.history import comparison, history_service
from src.history.models import ChangeType
from src.storage import apartment_history_repository, apartment_repository, search_memory_repository
from src.storage.models import (
    Apartment,
    ApartmentAvailabilityHistoryEntry,
    ApartmentImage,
    ApartmentPriceHistoryEntry,
)


def process_listing(
    conn: sqlite3.Connection,
    raw: RawListing,
    platform_id: str,
    search_id: str | None = None,
) -> Apartment:
    """Normalize one RawListing and write it, following the write sequence in
    docs/07_Analysis_Engine.md: insert (plus initial history, change-log rows, and
    images) if this (platform_id, platform_listing_id) hasn't been seen before;
    otherwise update current state and add a history row only for whichever of
    price/status/title/description/images actually changed. The Apartment History
    Engine (src/history/) owns the generic-field (title/description) and image-diff
    decisions; price/status keep using their pre-existing dedicated history tables.
    """
    fields = normalizer.normalize(raw)
    now = datetime.now(timezone.utc)

    existing = find_existing(conn, platform_id, fields["platform_listing_id"])

    if existing is None:
        apartment = Apartment(
            id=str(uuid.uuid4()),
            platform_id=platform_id,
            first_seen_at=now,
            last_seen_at=now,
            **fields,
        )
        apartment_repository.insert_apartment(conn, apartment)
        apartment_repository.add_price_history(
            conn,
            ApartmentPriceHistoryEntry(
                apartment_id=apartment.id, price=apartment.current_price, observed_at=now, search_id=search_id
            ),
        )
        apartment_repository.add_availability_history(
            conn,
            ApartmentAvailabilityHistoryEntry(
                apartment_id=apartment.id, status=apartment.current_status, observed_at=now, search_id=search_id
            ),
        )
        history_service.record_new_apartment(conn, apartment, now, search_id)
        _sync_images(conn, apartment.id, raw.image_urls, now, search_id)
        _record_observed(conn, apartment.id, now, search_id)
        return apartment

    price_changed = change_detector.price_changed(existing, fields["current_price"])
    status_changed = change_detector.status_changed(existing, fields["current_status"])

    apartment_repository.update_apartment_state(
        conn,
        apartment_id=existing.id,
        current_price=fields["current_price"],
        current_status=fields["current_status"],
        last_seen_at=now,
    )
    apartment_repository.update_apartment_details(
        conn, apartment_id=existing.id, title=fields["title"], description=fields.get("description")
    )

    if price_changed:
        apartment_repository.add_price_history(
            conn,
            ApartmentPriceHistoryEntry(
                apartment_id=existing.id, price=fields["current_price"], observed_at=now, search_id=search_id
            ),
        )
    if status_changed:
        apartment_repository.add_availability_history(
            conn,
            ApartmentAvailabilityHistoryEntry(
                apartment_id=existing.id, status=fields["current_status"], observed_at=now, search_id=search_id
            ),
        )

    history_service.record_reobservation(conn, existing, fields, now, search_id)
    _sync_images(conn, existing.id, raw.image_urls, now, search_id)
    _record_observed(conn, existing.id, now, search_id)

    existing.current_price = fields["current_price"]
    existing.current_status = fields["current_status"]
    existing.title = fields["title"]
    existing.description = fields.get("description")
    existing.last_seen_at = now
    return existing


def process_listings(
    conn: sqlite3.Connection,
    raw_listings: list[RawListing],
    platform_id: str,
    search_id: str | None = None,
) -> list[Apartment]:
    return [process_listing(conn, raw, platform_id, search_id) for raw in raw_listings]


def _record_observed(conn: sqlite3.Connection, apartment_id: str, now: datetime, search_id: str | None) -> None:
    """`search_observed_apartments` (v2.0 Step 3, docs/17_Search_Memory.md): the full set
    of apartments this search actually processed, regardless of whether they later
    survive ranking/filtering into `search_results` — what Search Memory's run-over-run
    comparison diffs. Like `apartment_image_events`, `search_id` is `NOT NULL`
    (an observation only makes sense in the context of the search that made it), so this
    is skipped — not the rest of the write sequence — when `process_listing()` is called
    without one (only direct unit tests; the real `RentalResearchAgent` always has one).

    v2.0 Step 4.5 note: this calls `storage.search_memory_repository` directly rather
    than going through `src/search_memory/search_memory_service.py` — reviewed
    deliberately, not an oversight. It's the same pattern this file already uses for
    `apartment_history_repository.add_image_event` and every `apartment_repository.add_*`
    call above: an unconditional append with no decision to make ("record that this
    apartment was observed," always, when there's a search to attribute it to). The
    History/Search Memory *service* layers exist for logic that decides *whether*
    something changed (`record_new_apartment`/`record_reobservation`,
    `record_completed_search`) — there's no such decision here, so routing through a
    service function would only add a pass-through wrapper with nothing to do. See
    docs/01_System_Architecture.md "Repository Writes vs. Service Layer" for the
    general rule this follows.
    """
    if search_id:
        search_memory_repository.add_observed_apartment(conn, search_id, apartment_id, now)


def _sync_images(
    conn: sqlite3.Connection, apartment_id: str, image_urls: list[str], now: datetime, search_id: str | None
) -> None:
    """Image Change Detection (docs/07_Analysis_Engine.md): diffs the apartment's
    currently-known (`is_current = 1`) image set against this observation's
    `image_urls`. Used for both a brand-new apartment (no current images yet, so every
    URL comes back "added" in original listing order — the same behavior V1 always
    had) and a re-observation (genuinely new capability in v2.0 Step 2): downloads and
    inserts any newly-added image, flips any missing one to `is_current = 0` (never
    deletes the row — Principle 1), and logs an `apartment_image_events` row for each,
    when a search context is known. `apartment_image_events.search_id` is NOT NULL —
    logging is skipped (not the download/flip itself) when `search_id` is None, which
    only happens in tests that call `process_listing` directly without a real search.
    """
    current_images = [image for image in apartment_repository.get_images(conn, apartment_id) if image.is_current]
    old_urls = [image.source_url for image in current_images]
    current_by_url = {image.source_url: image for image in current_images}

    changes = comparison.compare_images(apartment_id, old_urls, image_urls, now, search_id=search_id)

    position = len(old_urls)
    for change in changes:
        if change.change_type == ChangeType.IMAGE_ADDED:
            url = change.new_value
            suffix = Path(url).suffix or ".jpg"
            filename = f"{position}{suffix}"
            local_path = image_collector.collect_image(apartment_id, url, filename)
            apartment_repository.add_image(
                conn,
                ApartmentImage(
                    apartment_id=apartment_id,
                    source_url=url,
                    local_path=str(local_path),
                    position=position,
                    downloaded_at=now,
                ),
            )
            position += 1
            event_type, event_url = "added", url
        else:
            image = current_by_url.get(change.old_value)
            if image is not None:
                apartment_repository.mark_image_not_current(conn, image.id)
            event_type, event_url = "removed", change.old_value

        if search_id:
            apartment_history_repository.add_image_event(conn, apartment_id, event_type, event_url, search_id, now)
