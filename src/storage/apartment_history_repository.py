"""Persistence for `apartment_change_log` and `apartment_image_events` — the two
generic v2.0 history tables (schema added in migration 0001, Sprint V2.0.1; real
read/write logic added in v2.0 Step 2). Same convention as apartment_repository.py:
pure data access, no decisions about *when* to write — that's src/history/ and
analyzers/engine.py's job (docs/01_System_Architecture.md).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.storage.models import ApartmentChangeLogEntry, ApartmentImageEvent, iso, parse_iso


def add_change_log_entry(
    conn: sqlite3.Connection,
    apartment_id: str,
    field_name: str,
    old_value: str | None,
    new_value: str,
    observed_at: datetime,
    search_id: str | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO apartment_change_log "
        "(apartment_id, field_name, old_value, new_value, search_id, observed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (apartment_id, field_name, old_value, new_value, search_id, iso(observed_at)),
    )
    return cursor.lastrowid


def get_change_log(conn: sqlite3.Connection, apartment_id: str) -> list[ApartmentChangeLogEntry]:
    rows = conn.execute(
        "SELECT * FROM apartment_change_log WHERE apartment_id = ? ORDER BY observed_at",
        (apartment_id,),
    ).fetchall()
    return [
        ApartmentChangeLogEntry(
            id=row["id"],
            apartment_id=row["apartment_id"],
            field_name=row["field_name"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            search_id=row["search_id"],
            observed_at=parse_iso(row["observed_at"]),
        )
        for row in rows
    ]


def add_image_event(
    conn: sqlite3.Connection,
    apartment_id: str,
    event: str,
    source_url: str,
    search_id: str,
    observed_at: datetime,
) -> int:
    cursor = conn.execute(
        "INSERT INTO apartment_image_events "
        "(apartment_id, event, source_url, search_id, observed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (apartment_id, event, source_url, search_id, iso(observed_at)),
    )
    return cursor.lastrowid


def get_image_events(conn: sqlite3.Connection, apartment_id: str) -> list[ApartmentImageEvent]:
    rows = conn.execute(
        "SELECT * FROM apartment_image_events WHERE apartment_id = ? ORDER BY observed_at",
        (apartment_id,),
    ).fetchall()
    return [
        ApartmentImageEvent(
            id=row["id"],
            apartment_id=row["apartment_id"],
            event=row["event"],
            source_url=row["source_url"],
            search_id=row["search_id"],
            observed_at=parse_iso(row["observed_at"]),
        )
        for row in rows
    ]
