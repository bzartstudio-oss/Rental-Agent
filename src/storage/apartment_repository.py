"""Persistence for `apartments` and its three history/detail tables.

This module is deliberately just data access — insert/read primitives, nothing that
decides *when* a new history row should be written. That decision (has the price
actually changed?) belongs to analyzers/change_detector.py; this module just does
whatever write it's told to. Keeping that boundary is what docs/01_System_Architecture.md
means by "storage/ must not contain business rules about what to store."

Every function takes an open `sqlite3.Connection` (not a `Database`) as its first argument,
so a caller can compose several writes — e.g. insert an apartment and its initial history
row — inside one `Database.transaction()` block and have them commit or roll back together.
"""

from __future__ import annotations

import json
import sqlite3

from src.storage.models import (
    Apartment,
    ApartmentAvailabilityHistoryEntry,
    ApartmentImage,
    ApartmentPriceHistoryEntry,
    iso,
    parse_iso,
)


def insert_apartment(conn: sqlite3.Connection, apartment: Apartment) -> None:
    conn.execute(
        """
        INSERT INTO apartments (
            id, platform_id, platform_listing_id, title, bedrooms, bathrooms, sqft,
            address_raw, address_normalized, latitude, longitude, url,
            current_price, current_status, first_seen_at, last_seen_at, merged_into_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            apartment.id,
            apartment.platform_id,
            apartment.platform_listing_id,
            apartment.title,
            apartment.bedrooms,
            apartment.bathrooms,
            apartment.sqft,
            apartment.address_raw,
            json.dumps(apartment.address_normalized) if apartment.address_normalized else None,
            apartment.latitude,
            apartment.longitude,
            apartment.url,
            apartment.current_price,
            apartment.current_status,
            iso(apartment.first_seen_at),
            iso(apartment.last_seen_at),
            apartment.merged_into_id,
        ),
    )


def update_apartment_state(
    conn: sqlite3.Connection,
    apartment_id: str,
    current_price: float,
    current_status: str,
    last_seen_at,
) -> None:
    """Updates only the fields a re-observation of an existing listing can change.
    Does not touch first_seen_at, id, or platform identity — those are set once at insert.
    """
    conn.execute(
        "UPDATE apartments SET current_price = ?, current_status = ?, last_seen_at = ? WHERE id = ?",
        (current_price, current_status, iso(last_seen_at), apartment_id),
    )


def get_apartment(conn: sqlite3.Connection, apartment_id: str) -> Apartment | None:
    row = conn.execute("SELECT * FROM apartments WHERE id = ?", (apartment_id,)).fetchone()
    return _row_to_apartment(row) if row else None


def get_apartment_by_platform_listing(
    conn: sqlite3.Connection, platform_id: str, platform_listing_id: str
) -> Apartment | None:
    """The identity lookup used by the Analysis Engine's deduplicator (docs/07_Analysis_Engine.md)
    to decide whether a raw listing is a new apartment or a re-observation of one already known.
    """
    row = conn.execute(
        "SELECT * FROM apartments WHERE platform_id = ? AND platform_listing_id = ?",
        (platform_id, platform_listing_id),
    ).fetchone()
    return _row_to_apartment(row) if row else None


def _row_to_apartment(row: sqlite3.Row) -> Apartment:
    return Apartment(
        id=row["id"],
        platform_id=row["platform_id"],
        platform_listing_id=row["platform_listing_id"],
        title=row["title"],
        bedrooms=row["bedrooms"],
        bathrooms=row["bathrooms"],
        sqft=row["sqft"],
        address_raw=row["address_raw"],
        address_normalized=json.loads(row["address_normalized"]) if row["address_normalized"] else None,
        latitude=row["latitude"],
        longitude=row["longitude"],
        url=row["url"],
        current_price=row["current_price"],
        current_status=row["current_status"],
        first_seen_at=parse_iso(row["first_seen_at"]),
        last_seen_at=parse_iso(row["last_seen_at"]),
        merged_into_id=row["merged_into_id"],
    )


def add_price_history(conn: sqlite3.Connection, entry: ApartmentPriceHistoryEntry) -> int:
    cursor = conn.execute(
        "INSERT INTO apartment_price_history (apartment_id, price, observed_at, search_id) VALUES (?, ?, ?, ?)",
        (entry.apartment_id, entry.price, iso(entry.observed_at), entry.search_id),
    )
    return cursor.lastrowid


def get_price_history(conn: sqlite3.Connection, apartment_id: str) -> list[ApartmentPriceHistoryEntry]:
    rows = conn.execute(
        "SELECT * FROM apartment_price_history WHERE apartment_id = ? ORDER BY observed_at",
        (apartment_id,),
    ).fetchall()
    return [
        ApartmentPriceHistoryEntry(
            id=row["id"],
            apartment_id=row["apartment_id"],
            price=row["price"],
            observed_at=parse_iso(row["observed_at"]),
            search_id=row["search_id"],
        )
        for row in rows
    ]


def add_availability_history(conn: sqlite3.Connection, entry: ApartmentAvailabilityHistoryEntry) -> int:
    cursor = conn.execute(
        "INSERT INTO apartment_availability_history (apartment_id, status, observed_at, search_id) VALUES (?, ?, ?, ?)",
        (entry.apartment_id, entry.status, iso(entry.observed_at), entry.search_id),
    )
    return cursor.lastrowid


def get_availability_history(
    conn: sqlite3.Connection, apartment_id: str
) -> list[ApartmentAvailabilityHistoryEntry]:
    rows = conn.execute(
        "SELECT * FROM apartment_availability_history WHERE apartment_id = ? ORDER BY observed_at",
        (apartment_id,),
    ).fetchall()
    return [
        ApartmentAvailabilityHistoryEntry(
            id=row["id"],
            apartment_id=row["apartment_id"],
            status=row["status"],
            observed_at=parse_iso(row["observed_at"]),
            search_id=row["search_id"],
        )
        for row in rows
    ]


def add_image(conn: sqlite3.Connection, image: ApartmentImage) -> int:
    cursor = conn.execute(
        "INSERT INTO apartment_images (apartment_id, source_url, local_path, position, downloaded_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (image.apartment_id, image.source_url, image.local_path, image.position, iso(image.downloaded_at)),
    )
    return cursor.lastrowid


def get_images(conn: sqlite3.Connection, apartment_id: str) -> list[ApartmentImage]:
    rows = conn.execute(
        "SELECT * FROM apartment_images WHERE apartment_id = ? ORDER BY position",
        (apartment_id,),
    ).fetchall()
    return [
        ApartmentImage(
            id=row["id"],
            apartment_id=row["apartment_id"],
            source_url=row["source_url"],
            local_path=row["local_path"],
            position=row["position"],
            downloaded_at=parse_iso(row["downloaded_at"]),
        )
        for row in rows
    ]
