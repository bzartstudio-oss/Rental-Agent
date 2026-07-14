"""Repository layer for the `platforms` table — the Platform Registry
(docs/05_Platform_Discovery.md). Pure data access: register a platform, look one up,
list active ones. No decision logic about *which* platforms apply to a given search —
that's DiscoveryAgent's job (discovery_agent.py).

This lives in discovery/, not storage/, because it's conceptually part of "how the system
knows what platforms exist" rather than generic persistence — see the module table in
docs/01_System_Architecture.md.
"""

from __future__ import annotations

import sqlite3

from src.storage.models import Platform, iso, parse_iso


def register_platform(conn: sqlite3.Connection, platform: Platform) -> None:
    """Add a platform to the registry. Raises sqlite3.IntegrityError if `platform.id` is
    already registered — re-registering under the same id is a bug to surface, not
    something to silently upsert past.
    """
    conn.execute(
        """
        INSERT INTO platforms (id, name, base_url, connector_module, is_active, created_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            platform.id,
            platform.name,
            platform.base_url,
            platform.connector_module,
            int(platform.is_active),
            iso(platform.created_at),
            platform.notes,
        ),
    )


def get_platform(conn: sqlite3.Connection, platform_id: str) -> Platform | None:
    row = conn.execute("SELECT * FROM platforms WHERE id = ?", (platform_id,)).fetchone()
    return _row_to_platform(row) if row else None


def list_active_platforms(conn: sqlite3.Connection) -> list[Platform]:
    rows = conn.execute("SELECT * FROM platforms WHERE is_active = 1 ORDER BY id").fetchall()
    return [_row_to_platform(row) for row in rows]


def set_platform_active(conn: sqlite3.Connection, platform_id: str, is_active: bool) -> None:
    """The only supported way to retire a platform — flip is_active, never DELETE the row.
    Apartments and history rows reference platforms by FK; deleting a platform would either
    violate that constraint or orphan them, either way losing information (Principle 1).
    """
    conn.execute("UPDATE platforms SET is_active = ? WHERE id = ?", (int(is_active), platform_id))


def _row_to_platform(row: sqlite3.Row) -> Platform:
    return Platform(
        id=row["id"],
        name=row["name"],
        base_url=row["base_url"],
        connector_module=row["connector_module"],
        is_active=bool(row["is_active"]),
        created_at=parse_iso(row["created_at"]),
        notes=row["notes"],
    )
