"""Cache tests for GeoCache — src/geography/cache.py. Confirms the mission's own
words: "Repeated calculations should reuse cached results. Cache invalidation must be
configurable."
"""

from __future__ import annotations

import time
import unittest

from src.geography.cache import GeoCache


class GeoCacheTests(unittest.TestCase):
    def test_set_then_get_returns_the_cached_value(self) -> None:
        cache = GeoCache()
        cache.set("k", {"distance_km": 1.0})
        self.assertEqual(cache.get("k"), {"distance_km": 1.0})

    def test_get_on_an_unset_key_is_a_miss(self) -> None:
        cache = GeoCache()
        self.assertIsNone(cache.get("does-not-exist"))

    def test_entry_expires_after_its_ttl(self) -> None:
        cache = GeoCache(default_ttl_seconds=1)
        cache.set("k", "v")
        self.assertEqual(cache.get("k"), "v")
        time.sleep(1.1)
        self.assertIsNone(cache.get("k"))

    def test_per_entry_ttl_overrides_the_cache_default(self) -> None:
        cache = GeoCache(default_ttl_seconds=3600)
        cache.set("k", "v", ttl_seconds=1)
        time.sleep(1.1)
        self.assertIsNone(cache.get("k"))

    def test_invalidate_removes_one_key_configurably(self) -> None:
        cache = GeoCache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.invalidate("k1")
        self.assertIsNone(cache.get("k1"))
        self.assertEqual(cache.get("k2"), "v2")

    def test_invalidate_unset_key_does_not_raise(self) -> None:
        cache = GeoCache()
        cache.invalidate("does-not-exist")  # must not raise

    def test_clear_removes_everything(self) -> None:
        cache = GeoCache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_len_reflects_current_entry_count(self) -> None:
        cache = GeoCache()
        self.assertEqual(len(cache), 0)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        self.assertEqual(len(cache), 2)

    def test_make_key_is_stable_for_the_same_parts(self) -> None:
        key1 = GeoCache.make_key("distance", "haversine", (1.0, 2.0), (3.0, 4.0), "walking")
        key2 = GeoCache.make_key("distance", "haversine", (1.0, 2.0), (3.0, 4.0), "walking")
        self.assertEqual(key1, key2)

    def test_make_key_differs_for_different_parts(self) -> None:
        key1 = GeoCache.make_key("distance", "haversine", (1.0, 2.0), (3.0, 4.0), "walking")
        key2 = GeoCache.make_key("distance", "haversine", (1.0, 2.0), (3.0, 4.0), "driving")
        self.assertNotEqual(key1, key2)


if __name__ == "__main__":
    unittest.main()
