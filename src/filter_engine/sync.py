"""Syncs every registered filter's `FilterMetadata` into the real `filter_definitions`
table — the same "sync a known catalog into the database at startup" pattern
`DiscoveryAgent.sync_platforms()` already established for platforms. See
docs/25_Dynamic_Filter_Engine.md "Plugin System".
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.filter_engine.registry import FilterRegistry
from src.storage import filter_definitions_repository
from src.storage.models import FilterDefinitionRecord


def sync_filter_definitions(conn: sqlite3.Connection) -> int:
    """Upserts every currently-registered filter's metadata — idempotent, safe to
    call on every app startup (mirrors `sync_platforms()`'s own idempotence).
    Returns the number of definitions synced.
    """
    now = datetime.now(timezone.utc)
    count = 0
    for filter_instance in FilterRegistry.all():
        metadata = filter_instance.metadata()
        filter_definitions_repository.upsert_definition(
            conn,
            FilterDefinitionRecord(
                key=metadata.key,
                display_name=metadata.display_name,
                category=metadata.category,
                value_type=metadata.value_type,
                applicable_rental_types=metadata.applicable_rental_types,
                description=metadata.description,
                created_at=now,
            ),
        )
        count += 1
    return count
