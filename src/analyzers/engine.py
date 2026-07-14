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
from src.storage import apartment_repository
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
    docs/07_Analysis_Engine.md: insert (plus initial history and images) if this
    (platform_id, platform_listing_id) hasn't been seen before; otherwise update current
    state and add a history row only for whichever of price/status actually changed.
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
        _collect_images(conn, apartment.id, raw.image_urls, now)
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

    existing.current_price = fields["current_price"]
    existing.current_status = fields["current_status"]
    existing.last_seen_at = now
    return existing


def process_listings(
    conn: sqlite3.Connection,
    raw_listings: list[RawListing],
    platform_id: str,
    search_id: str | None = None,
) -> list[Apartment]:
    return [process_listing(conn, raw, platform_id, search_id) for raw in raw_listings]


def _collect_images(conn: sqlite3.Connection, apartment_id: str, image_urls: list[str], now: datetime) -> None:
    """Only for newly-discovered apartments (V1 scope) — re-observed apartments don't
    re-download images every search, to avoid piling up duplicate image rows for
    unchanged photos. Revisit if a platform is found to genuinely change its images
    over time in a way that matters.
    """
    for index, url in enumerate(image_urls):
        suffix = Path(url).suffix or ".jpg"
        filename = f"{index}{suffix}"
        local_path = image_collector.collect_image(apartment_id, url, filename)
        apartment_repository.add_image(
            conn,
            ApartmentImage(
                apartment_id=apartment_id,
                source_url=url,
                local_path=str(local_path),
                position=index,
                downloaded_at=now,
            ),
        )
