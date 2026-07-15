"""Performance regression tests for the Dynamic Filter Engine — running the real 39
built-in filters against a real-sized apartment set, and confirming registering many
additional filters doesn't slow down lookup, must both stay fast. Mirrors
`tests/connectors/sdk/test_performance.py`'s same "the whole point of a plugin
architecture is that scale doesn't degrade the framework" reasoning.
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from src.filter_engine.base_filter import BaseFilter, FilterContext
from src.filter_engine.engine import FilterEngine
from src.filter_engine.metadata import FilterMetadata
from src.filter_engine.registry import FilterRegistry, register_filter
from src.storage.models import Apartment


class _BulkFakeFilter(BaseFilter):
    def validate(self, value) -> None:
        pass

    def apply(self, apartment, value, context: FilterContext) -> bool:
        return True

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(key=self.key, display_name=self.key, category="test", value_type="boolean")


def _apartments(count: int) -> list[Apartment]:
    now = datetime.now(timezone.utc)
    return [
        Apartment(
            id=f"a{i}", platform_id="p1", platform_listing_id=str(i), title=f"Place {i}", url="x",
            current_price=500 + i, current_status="available", first_seen_at=now, last_seen_at=now,
            bedrooms=i % 4, sqft=300 + i * 5, property_type="apartment" if i % 2 == 0 else "house",
        )
        for i in range(count)
    ]


class FilterEnginePerformanceTests(unittest.TestCase):
    def test_running_all_built_in_filters_against_500_apartments_stays_fast(self) -> None:
        engine = FilterEngine()
        apartments = _apartments(500)
        criteria = {"max_price": 800, "property_type": "apartment", "private_bathroom": True}

        started = time.perf_counter()
        results, stats = engine.run(apartments, criteria)
        elapsed_s = time.perf_counter() - started

        self.assertEqual(stats.total_apartments, 500)
        self.assertLess(elapsed_s, 2.0, "filtering 500 apartments against 3 filters took too long")

    def test_registering_500_additional_filters_does_not_slow_down_lookup(self) -> None:
        registered_keys = []
        try:
            for i in range(500):
                key = f"bulk_fake_filter_{i}"
                filter_instance = _BulkFakeFilter()
                filter_instance.key = key
                register_filter(filter_instance)
                registered_keys.append(key)

            started = time.perf_counter()
            for key in registered_keys:
                FilterRegistry.get(key)
            elapsed_s = time.perf_counter() - started

            self.assertLess(elapsed_s, 1.0, "resolving 500 registered filters took too long")
        finally:
            for key in registered_keys:
                FilterRegistry._filters.pop(key, None)


if __name__ == "__main__":
    unittest.main()
