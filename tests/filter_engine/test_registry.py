"""Unit tests for FilterRegistry — src/filter_engine/registry.py. Uses a private
`_FakeRegistry` subclass with its own `_filters` dict, never touching the real,
shared `FilterRegistry` (which already holds all 39 built-in filters by the time any
test runs) — the same isolation strategy the Provider Abstraction Layer's own
registry tests use.
"""

from __future__ import annotations

import unittest

from src.filter_engine.base_filter import BaseFilter, FilterContext
from src.filter_engine.exceptions import FilterConfigurationError
from src.filter_engine.metadata import FilterMetadata
from src.filter_engine.registry import FilterRegistry


class _FakeRegistry(FilterRegistry):
    _filters: dict = {}


class _FakeFilter(BaseFilter):
    key = "fake"

    def validate(self, value):
        pass

    def apply(self, apartment, value, context: FilterContext) -> bool:
        return True

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(key=self.key, display_name="Fake", category="test", value_type="boolean")


class FilterRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRegistry.reset()

    def test_register_then_get_returns_the_same_instance(self) -> None:
        filter_instance = _FakeFilter()
        _FakeRegistry.register(filter_instance)
        self.assertIs(_FakeRegistry.get("fake"), filter_instance)

    def test_get_unknown_filter_raises_configuration_error(self) -> None:
        with self.assertRaises(FilterConfigurationError):
            _FakeRegistry.get("does-not-exist")

    def test_register_rejects_non_basefilter_objects(self) -> None:
        with self.assertRaises(FilterConfigurationError):
            _FakeRegistry.register(object())  # type: ignore[arg-type]

    def test_register_rejects_a_filter_with_no_key(self) -> None:
        class _NoKey(BaseFilter):
            key = ""

            def validate(self, value):
                pass

            def apply(self, apartment, value, context):
                return True

            def metadata(self):
                return FilterMetadata(key="", display_name="x", category="test", value_type="boolean")

        with self.assertRaises(FilterConfigurationError):
            _FakeRegistry.register(_NoKey())

    def test_all_returns_every_registered_filter(self) -> None:
        _FakeRegistry.register(_FakeFilter())
        self.assertEqual([f.key for f in _FakeRegistry.all()], ["fake"])

    def test_is_registered(self) -> None:
        self.assertFalse(_FakeRegistry.is_registered("fake"))
        _FakeRegistry.register(_FakeFilter())
        self.assertTrue(_FakeRegistry.is_registered("fake"))

    def test_reset_clears_everything(self) -> None:
        _FakeRegistry.register(_FakeFilter())
        _FakeRegistry.reset()
        self.assertEqual(_FakeRegistry.all(), [])

    def test_real_registry_has_all_39_built_in_filters(self) -> None:
        """Not isolated — proves the real, shared `FilterRegistry` genuinely holds
        every built-in filter at import time, not just the fake one used above.
        """
        self.assertEqual(len(FilterRegistry.all()), 39)
        self.assertTrue(FilterRegistry.is_registered("max_price"))
        self.assertTrue(FilterRegistry.is_registered("private_bathroom"))


if __name__ == "__main__":
    unittest.main()
