"""Persistence for `knowledge_entries` — the Knowledge Database (docs/02_Folder_Guide.md
data/knowledge_base/). Curated reference data, not raw scrape output: consulted by
analyzers/enricher.py and potentially ranking, never written to by a connector.
"""

from __future__ import annotations

import sqlite3

from src.storage.models import KnowledgeEntry, iso, parse_iso


def upsert_knowledge_entry(conn: sqlite3.Connection, entry: KnowledgeEntry) -> None:
    """Insert, or overwrite if (category, key) already exists — unlike the apartment
    history tables, knowledge entries are current-value facts (e.g. "average rent in
    neighborhood X"), not an observation log, so overwriting is correct here.
    """
    conn.execute(
        """
        INSERT INTO knowledge_entries (category, key, value_json, source, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (category, key) DO UPDATE SET
            value_json = excluded.value_json,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (entry.category, entry.key, entry.value_json, entry.source, iso(entry.updated_at)),
    )


def get_knowledge_entry(conn: sqlite3.Connection, category: str, key: str) -> KnowledgeEntry | None:
    row = conn.execute(
        "SELECT * FROM knowledge_entries WHERE category = ? AND key = ?",
        (category, key),
    ).fetchone()
    if row is None:
        return None
    return KnowledgeEntry(
        id=row["id"],
        category=row["category"],
        key=row["key"],
        value_json=row["value_json"],
        source=row["source"],
        updated_at=parse_iso(row["updated_at"]),
    )


def get_knowledge_by_category(conn: sqlite3.Connection, category: str) -> list[KnowledgeEntry]:
    rows = conn.execute(
        "SELECT * FROM knowledge_entries WHERE category = ? ORDER BY key",
        (category,),
    ).fetchall()
    return [
        KnowledgeEntry(
            id=row["id"],
            category=row["category"],
            key=row["key"],
            value_json=row["value_json"],
            source=row["source"],
            updated_at=parse_iso(row["updated_at"]),
        )
        for row in rows
    ]
