"""Within-platform duplicate detection (V1 scope) — see docs/07_Analysis_Engine.md.

Cross-platform de-duplication (the same physical apartment listed on two different
sites) is explicitly V2 (apartments.merged_into_id is reserved for it, unused here) —
this only answers "have we already seen this exact (platform, listing id) before?"
"""

from __future__ import annotations

import sqlite3

from src.storage import apartment_repository
from src.storage.models import Apartment


def find_existing(conn: sqlite3.Connection, platform_id: str, platform_listing_id: str) -> Apartment | None:
    return apartment_repository.get_apartment_by_platform_listing(conn, platform_id, platform_listing_id)
