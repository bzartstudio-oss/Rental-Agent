"""Persistence for `filter_definitions` (migration 0001) — designed for the Dynamic
Filter Engine, unused until v2.5 Step 9. Pure data access, same convention as every
other repository — no decision about *when* to sync lives here (that's
`filter_engine.sync_filter_definitions()`'s job).
"""

from __future__ import annotations

import json
import sqlite3

from src.storage.models import FilterDefinitionRecord, iso, parse_iso


def upsert_definition(conn: sqlite3.Connection, definition: FilterDefinitionRecord) -> None:
    conn.execute(
        """
        INSERT INTO filter_definitions (key, display_name, category, value_type, applicable_rental_types_json, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            display_name = excluded.display_name,
            category = excluded.category,
            value_type = excluded.value_type,
            applicable_rental_types_json = excluded.applicable_rental_types_json,
            description = excluded.description
        """,
        (
            definition.key,
            definition.display_name,
            definition.category,
            definition.value_type,
            json.dumps(definition.applicable_rental_types),
            definition.description,
            iso(definition.created_at),
        ),
    )


def get_definition(conn: sqlite3.Connection, key: str) -> FilterDefinitionRecord | None:
    row = conn.execute("SELECT * FROM filter_definitions WHERE key = ?", (key,)).fetchone()
    return _row_to_definition(row) if row else None


def list_definitions(conn: sqlite3.Connection) -> list[FilterDefinitionRecord]:
    rows = conn.execute("SELECT * FROM filter_definitions ORDER BY key").fetchall()
    return [_row_to_definition(row) for row in rows]


def _row_to_definition(row: sqlite3.Row) -> FilterDefinitionRecord:
    return FilterDefinitionRecord(
        key=row["key"],
        display_name=row["display_name"],
        category=row["category"],
        value_type=row["value_type"],
        applicable_rental_types=json.loads(row["applicable_rental_types_json"]),
        description=row["description"],
        created_at=parse_iso(row["created_at"]),
    )
