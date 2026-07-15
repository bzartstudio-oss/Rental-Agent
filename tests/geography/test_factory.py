"""Unit tests for GeoProviderFactory — src/geography/factory.py."""

from __future__ import annotations

import unittest

from src.geography.exceptions import GeoProviderConfigurationError
from src.geography.factory import GeoProviderFactory
from src.geography.registry import GeoProviderRegistry


class GeoProviderFactoryTests(unittest.TestCase):
    def test_get_resolves_the_real_haversine_provider(self) -> None:
        provider = GeoProviderFactory.get("haversine")
        self.assertEqual(provider.provider_id, "haversine")

    def test_get_unknown_id_raises_configuration_error(self) -> None:
        with self.assertRaises(GeoProviderConfigurationError):
            GeoProviderFactory.get("does-not-exist")

    def test_get_best_available_returns_a_provider_that_is_actually_available(self) -> None:
        provider = GeoProviderFactory.get_best_available()
        self.assertTrue(provider.is_available())

    def test_get_best_available_raises_when_nothing_is_registered(self) -> None:
        class _EmptyRegistry(GeoProviderRegistry):
            _providers: dict = {}

        import src.geography.factory as factory_module

        original = factory_module.GeoProviderRegistry
        factory_module.GeoProviderRegistry = _EmptyRegistry
        try:
            with self.assertRaises(GeoProviderConfigurationError):
                GeoProviderFactory.get_best_available()
        finally:
            factory_module.GeoProviderRegistry = original


if __name__ == "__main__":
    unittest.main()
