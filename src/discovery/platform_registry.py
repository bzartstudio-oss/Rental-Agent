"""Repository layer for the `platforms` table — the Platform Registry
(docs/05_Platform_Discovery.md). Pure data access: register/read/update platforms. No
decision logic about duplicates or what counts as "new" — that's DiscoveryAgent's job
(discovery_agent.py).

Lives in discovery/, not storage/, because it's conceptually part of "how the system
knows what platforms exist" rather than generic persistence — see the module table in
docs/01_System_Architecture.md.
"""

from __future__ import annotations

import json
import sqlite3

from src.storage.models import Platform, iso, parse_iso


def register_platform(conn: sqlite3.Connection, platform: Platform) -> None:
    """Add a platform to the registry. Raises sqlite3.IntegrityError if `platform.id` is
    already registered — re-registering under the same id is a bug to surface, not
    something to silently upsert past. Use update_platform_metadata() for platforms
    already known (that's the distinction DiscoveryAgent.sync_platforms() makes).
    """
    conn.execute(
        """
        INSERT INTO platforms (
            id, name, country, supported_cities, rental_types, homepage, search_url,
            requires_login, connector_available, connector_name, last_verified,
            discovery_method, notes, created_at,
            connector_version, reliability_score, success_rate, avg_response_time_ms,
            avg_apartment_count, duplicate_percentage
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            platform.id,
            platform.name,
            platform.country,
            json.dumps(platform.supported_cities),
            json.dumps(platform.rental_types),
            platform.homepage,
            platform.search_url,
            int(platform.requires_login),
            int(platform.connector_available),
            platform.connector_name,
            iso(platform.last_verified) if platform.last_verified else None,
            platform.discovery_method,
            platform.notes,
            iso(platform.created_at),
            # v2.0 (migration 0001) — Platform Intelligence rollups; always None at
            # registration time, populated later by the Knowledge Engine (not this sprint).
            platform.connector_version,
            platform.reliability_score,
            platform.success_rate,
            platform.avg_response_time_ms,
            platform.avg_apartment_count,
            platform.duplicate_percentage,
        ),
    )


def get_platform(conn: sqlite3.Connection, platform_id: str) -> Platform | None:
    row = conn.execute("SELECT * FROM platforms WHERE id = ?", (platform_id,)).fetchone()
    return _row_to_platform(row) if row else None


def list_all_platforms(conn: sqlite3.Connection) -> list[Platform]:
    """Every known platform, regardless of connector_available — the "load existing
    platforms" step of DiscoveryAgent.sync_platforms().
    """
    rows = conn.execute("SELECT * FROM platforms ORDER BY id").fetchall()
    return [_row_to_platform(row) for row in rows]


def list_connector_available_platforms(conn: sqlite3.Connection) -> list[Platform]:
    """Platforms this system can actually search — what DiscoveryAgent.discover() (the
    search-facing method) returns.
    """
    rows = conn.execute("SELECT * FROM platforms WHERE connector_available = 1 ORDER BY id").fetchall()
    return [_row_to_platform(row) for row in rows]


def update_platform_metadata(conn: sqlite3.Connection, platform_id: str, updated: Platform) -> None:
    """Overwrite an existing platform's metadata (everything except id/created_at) and
    bump last_verified to `updated.last_verified`. Used when DiscoveryAgent detects a
    duplicate and refreshes its record instead of inserting a second row.
    """
    conn.execute(
        """
        UPDATE platforms SET
            name = ?, country = ?, supported_cities = ?, rental_types = ?, homepage = ?,
            search_url = ?, requires_login = ?, connector_available = ?, connector_name = ?,
            last_verified = ?, discovery_method = ?, notes = ?
        WHERE id = ?
        """,
        (
            updated.name,
            updated.country,
            json.dumps(updated.supported_cities),
            json.dumps(updated.rental_types),
            updated.homepage,
            updated.search_url,
            int(updated.requires_login),
            int(updated.connector_available),
            updated.connector_name,
            iso(updated.last_verified) if updated.last_verified else None,
            updated.discovery_method,
            updated.notes,
            platform_id,
        ),
    )


def mark_connector_unavailable(conn: sqlite3.Connection, platform_id: str, note: str | None = None) -> None:
    """Explicitly flags a platform as known-but-unsupported (docs/05_Platform_Discovery.md
    behavior 5) — sets connector_available = 0 and connector_name = NULL without touching
    any other metadata. The platform stays in the registry either way (Principle 1).
    """
    platform = get_platform(conn, platform_id)
    if platform is None:
        raise KeyError(f"Cannot mark unknown platform {platform_id!r} unsupported — it isn't registered")

    conn.execute(
        "UPDATE platforms SET connector_available = 0, connector_name = NULL, notes = ? WHERE id = ?",
        (note if note is not None else platform.notes, platform_id),
    )


def _row_to_platform(row: sqlite3.Row) -> Platform:
    return Platform(
        id=row["id"],
        name=row["name"],
        country=row["country"],
        supported_cities=json.loads(row["supported_cities"]),
        rental_types=json.loads(row["rental_types"]),
        homepage=row["homepage"],
        search_url=row["search_url"],
        requires_login=bool(row["requires_login"]),
        connector_available=bool(row["connector_available"]),
        connector_name=row["connector_name"],
        last_verified=parse_iso(row["last_verified"]) if row["last_verified"] else None,
        discovery_method=row["discovery_method"],
        notes=row["notes"],
        created_at=parse_iso(row["created_at"]),
        # v2.0 (migration 0001) — Platform Intelligence rollups, all nullable.
        connector_version=row["connector_version"],
        reliability_score=row["reliability_score"],
        success_rate=row["success_rate"],
        avg_response_time_ms=row["avg_response_time_ms"],
        avg_apartment_count=row["avg_apartment_count"],
        duplicate_percentage=row["duplicate_percentage"],
    )
