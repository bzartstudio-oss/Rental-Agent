"""DiscoveryAgent — decides which registered platforms apply to a SearchRequest.

V1.0 scope (docs/05_Platform_Discovery.md): this is close to "all active platforms" —
location-based platform filtering isn't built yet, since there's no evidence it's needed
with only a handful of platforms to reason about. `discover()` already takes a `request`
parameter, even though V1.0 ignores its contents, so this interface doesn't need to change
once search/search_request.py (Phase 4) exists and starts passing a real SearchRequest.
"""

from __future__ import annotations

from src.discovery.platform_registry import list_active_platforms
from src.storage.database import Database
from src.storage.models import Platform


class DiscoveryAgent:
    def __init__(self, db: Database) -> None:
        self._db = db

    def discover(self, request: object = None) -> list[Platform]:
        """Return the platforms relevant to `request`.

        V1.0: every active platform, regardless of what `request` contains — see the
        module docstring for why. `request` is accepted now so callers (and this method's
        own future implementation) don't need a signature change when per-request
        filtering is actually built.
        """
        with self._db.transaction() as conn:
            return list_active_platforms(conn)
