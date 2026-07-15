"""Unit tests for ProviderRegistry — src/providers/registry.py.

Uses a private subclass with its own `_providers` dict for every test, never touching
the real, shared `ProviderRegistry` (which already holds the real built-in providers
by the time any test runs, since `src.providers` eagerly imports them) — the same
isolation strategy the router tests use.
"""

from __future__ import annotations

import unittest

from src.providers.base import Provider, ProviderKind
from src.providers.exceptions import ProviderConfigurationError
from src.providers.registry import ProviderRegistry
from src.providers.scoring import ProviderMetadata


class _FakeRegistry(ProviderRegistry):
    _providers: dict = {}


class _FakeProvider(Provider):
    provider_id = "fake"
    kind = ProviderKind.DATA

    def is_available(self) -> bool:
        return True

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_id=self.provider_id, cost_score=0.0, freshness_score=1.0, quality_score=1.0)


class ProviderRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRegistry.reset()

    def test_register_then_get_returns_the_same_instance(self) -> None:
        provider = _FakeProvider()
        _FakeRegistry.register(provider)

        self.assertIs(_FakeRegistry.get("fake"), provider)

    def test_get_unknown_provider_raises_configuration_error(self) -> None:
        with self.assertRaises(ProviderConfigurationError):
            _FakeRegistry.get("does-not-exist")

    def test_register_rejects_non_provider_objects(self) -> None:
        with self.assertRaises(ProviderConfigurationError):
            _FakeRegistry.register(object())  # type: ignore[arg-type]

    def test_register_rejects_a_provider_with_no_provider_id(self) -> None:
        class _NoId(Provider):
            provider_id = ""
            kind = ProviderKind.DATA

            def is_available(self) -> bool:
                return True

            def metadata(self) -> ProviderMetadata:
                return ProviderMetadata(provider_id="", cost_score=0.0, freshness_score=0.0, quality_score=0.0)

        with self.assertRaises(ProviderConfigurationError):
            _FakeRegistry.register(_NoId())

    def test_all_filters_by_kind(self) -> None:
        class _AIFake(Provider):
            provider_id = "fake-ai"
            kind = ProviderKind.AI

            def is_available(self) -> bool:
                return True

            def metadata(self) -> ProviderMetadata:
                return ProviderMetadata(provider_id=self.provider_id, cost_score=0.0, freshness_score=0.0, quality_score=0.0)

        _FakeRegistry.register(_FakeProvider())
        _FakeRegistry.register(_AIFake())

        self.assertEqual([p.provider_id for p in _FakeRegistry.all(ProviderKind.DATA)], ["fake"])
        self.assertEqual([p.provider_id for p in _FakeRegistry.all(ProviderKind.AI)], ["fake-ai"])
        self.assertEqual(len(_FakeRegistry.all()), 2)

    def test_is_registered(self) -> None:
        self.assertFalse(_FakeRegistry.is_registered("fake"))
        _FakeRegistry.register(_FakeProvider())
        self.assertTrue(_FakeRegistry.is_registered("fake"))

    def test_reset_clears_everything(self) -> None:
        _FakeRegistry.register(_FakeProvider())
        _FakeRegistry.reset()
        self.assertEqual(_FakeRegistry.all(), [])


if __name__ == "__main__":
    unittest.main()
