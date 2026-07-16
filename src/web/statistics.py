"""`WebStatistics` — dashboard/health-page aggregate counts. See
docs/32_Web_Dashboard.md "System Health"/"Main Dashboard".

Simple `COUNT(*)` reads over existing tables — no existing repository exposes
a generic row-count function (each is scoped to its own domain's real query
patterns), so this module, the designated aggregation layer for the web
package (mirroring `monitoring/statistics.py`/`discovery/automatic/statistics.py`'s
own "computes aggregates from already-persisted data" role), reads them
directly rather than adding a one-off count method to every repository for a
single dashboard widget. Never a business calculation — only a count.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class WebStatistics:
    apartment_count: int
    search_count: int
    monitoring_event_count: int
    platform_count: int
    saved_search_count: int
    notification_preference_count: int
    discovery_candidate_count: int
    database_size_bytes: int

    @classmethod
    def collect(cls, conn: sqlite3.Connection, db_path) -> "WebStatistics":
        def count(table: str) -> int:
            return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]

        try:
            size = db_path.stat().st_size
        except OSError:
            size = 0

        return cls(
            apartment_count=count("apartments"),
            search_count=count("search_requests"),
            monitoring_event_count=count("monitoring_events"),
            platform_count=count("platforms"),
            saved_search_count=count("saved_searches"),
            notification_preference_count=count("notification_preferences"),
            discovery_candidate_count=count("platform_candidates"),
            database_size_bytes=size,
        )
