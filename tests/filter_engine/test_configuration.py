"""Unit tests for FilterConfiguration — src/filter_engine/configuration.py."""

from __future__ import annotations

import unittest

from src.filter_engine.configuration import FilterConfiguration


class FilterConfigurationTests(unittest.TestCase):
    def test_defaults_enable_every_filter(self) -> None:
        config = FilterConfiguration()
        self.assertIsNone(config.enabled_filter_keys)
        self.assertFalse(config.strict_validation)
        self.assertTrue(config.is_enabled("max_price"))
        self.assertTrue(config.is_enabled("anything_at_all"))

    def test_enabled_filter_keys_restricts_to_exactly_that_set(self) -> None:
        config = FilterConfiguration(enabled_filter_keys={"max_price", "min_price"})
        self.assertTrue(config.is_enabled("max_price"))
        self.assertFalse(config.is_enabled("currency"))

    def test_empty_enabled_set_disables_everything(self) -> None:
        config = FilterConfiguration(enabled_filter_keys=set())
        self.assertFalse(config.is_enabled("max_price"))


if __name__ == "__main__":
    unittest.main()
