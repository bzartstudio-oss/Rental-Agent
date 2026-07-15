"""Persistence for `geo_enrichment_history` (migration 0006, v2.5 Step 10) — pure
data access; deciding *when*/*what* to record is `geography.history`'s job. Mirrors
`filter_history_repository.py`'s exact shape.
"""

from __future__ import annotations

import json
import sqlite3

from src.storage.models import GeoEnrichmentHistoryEntry, iso, parse_iso


def add_execution(conn: sqlite3.Connection, entry: GeoEnrichmentHistoryEntry) -> int:
    cursor = conn.execute(
        """
        INSERT INTO geo_enrichment_history
            (apartment_id, search_id, provider_id, calculation_method, summary_json, confidence, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.apartment_id,
            entry.search_id,
            entry.provider_id,
            entry.calculation_method,
            json.dumps(entry.summary),
            entry.confidence,
            iso(entry.recorded_at),
        ),
    )
    return cursor.lastrowid


def get_history_for_apartment(conn: sqlite3.Connection, apartment_id: str) -> list[GeoEnrichmentHistoryEntry]:
    rows = conn.execute(
        "SELECT * FROM geo_enrichment_history WHERE apartment_id = ? ORDER BY recorded_at",
        (apartment_id,),
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def get_history_for_search(conn: sqlite3.Connection, search_id: str) -> list[GeoEnrichmentHistoryEntry]:
    rows = conn.execute(
        "SELECT * FROM geo_enrichment_history WHERE search_id = ? ORDER BY recorded_at",
        (search_id,),
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def _row_to_entry(row: sqlite3.Row) -> GeoEnrichmentHistoryEntry:
    return GeoEnrichmentHistoryEntry(
        id=row["id"],
        apartment_id=row["apartment_id"],
        search_id=row["search_id"],
        provider_id=row["provider_id"],
        calculation_method=row["calculation_method"],
        summary=json.loads(row["summary_json"]),
        confidence=row["confidence"],
        recorded_at=parse_iso(row["recorded_at"]),
    )
