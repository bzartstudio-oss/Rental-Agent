"""Unit tests for ProviderConfiguration — src/providers/configuration.py."""

from __future__ import annotations

import unittest

from src.providers.configuration import ProviderConfiguration


class ProviderConfigurationTests(unittest.TestCase):
    def test_defaults_match_a_sane_out_of_the_box_configuration(self) -> None:
        config = ProviderConfiguration()

        self.assertEqual(config.timeout_ms, 30_000)
        self.assertEqual(config.max_retries, 0)
        self.assertIsNone(config.rate_limit_per_minute)
        self.assertIsNone(config.credentials)

    def test_every_field_is_overridable(self) -> None:
        config = ProviderConfiguration(
            timeout_ms=5_000, max_retries=3, rate_limit_per_minute=10, credentials={"api_key": "x"}
        )

        self.assertEqual(config.timeout_ms, 5_000)
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.rate_limit_per_minute, 10)
        self.assertEqual(config.credentials, {"api_key": "x"})


if __name__ == "__main__":
    unittest.main()
