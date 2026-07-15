"""`GeoCache` — a real, generic, TTL-based in-memory cache for geographic
calculations. See docs/26_Geographic_Intelligence.md "Caching".

The Production Readiness Review (docs/23, Q4) found that **zero caching
infrastructure exists anywhere in this codebase** — this is the first one. Kept
deliberately generic (key → value, any value type) rather than baked into
`GeoProvider`/`GeographicEngine` directly, so the calculators (`DistanceCalculator`/
`TravelTimeCalculator`/`NearbySearch`) can all share one cache instance without
each reimplementing expiry logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_DEFAULT_TTL_SECONDS = 3600  # 1 hour — a real, tunable default, not a magic number


@dataclass
class _CacheEntry:
    value: Any
    cached_at: datetime
    ttl_seconds: int


class GeoCache:
    def __init__(self, default_ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._default_ttl_seconds = default_ttl_seconds

    def get(self, key: str) -> Any | None:
        """`None` for both "never cached" and "expired" — a cache miss is a cache
        miss either way; the caller always recomputes and calls `set()` again.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """`ttl_seconds=None` uses this cache's own default — "cache invalidation
        must be configurable" (the mission's words) means per-entry, per-cache, and
        via explicit `invalidate()`/`clear()`, not just one hardcoded expiry.
        """
        self._store[key] = _CacheEntry(
            value=value,
            cached_at=datetime.now(timezone.utc),
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds,
        )

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    def _is_expired(self, entry: _CacheEntry) -> bool:
        age_seconds = (datetime.now(timezone.utc) - entry.cached_at).total_seconds()
        return age_seconds > entry.ttl_seconds

    @staticmethod
    def make_key(*parts: object) -> str:
        """A stable, human-readable cache key from any number of parts — every
        calculator uses this instead of hand-rolling its own key format.
        """
        return "|".join(str(part) for part in parts)
