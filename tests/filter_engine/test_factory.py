"""Unit tests for FilterFactory — src/filter_engine/factory.py. `FilterFactory` has
no logic beyond delegating to `FilterRegistry.get()`, so these tests exercise it
against the real, shared registry, where the 39 built-in filters are already
self-registered at import time.
"""

from __future__ import annotations

import unittest

from src.filter_engine.exceptions import FilterConfigurationError
from src.filter_engine.factory import FilterFactory


class FilterFactoryTests(unittest.TestCase):
    def test_resolves_a_real_registered_filter(self) -> None:
        self.assertEqual(FilterFactory.get("max_price").key, "max_price")

    def test_returns_the_same_singleton_instance_every_call(self) -> None:
        self.assertIs(FilterFactory.get("max_price"), FilterFactory.get("max_price"))

    def test_raises_configuration_error_for_an_unknown_key(self) -> None:
        with self.assertRaises(FilterConfigurationError):
            FilterFactory.get("not-a-real-filter")


if __name__ == "__main__":
    unittest.main()
