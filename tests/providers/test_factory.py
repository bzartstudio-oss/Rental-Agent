"""Unit tests for ProviderFactory — src/providers/factory.py.

`ProviderFactory` has no logic beyond delegating to `ProviderRegistry.get()` (see its
own docstring for why: two classes for two reasons to change, not two competing
lookup mechanisms) — so these tests exercise it against the real, shared
`ProviderRegistry`, where the built-in providers are already self-registered at
import time, rather than a fake one.
"""

from __future__ import annotations

import unittest

from src.providers.exceptions import ProviderConfigurationError
from src.providers.factory import ProviderFactory
from src.providers.registry import ProviderRegistry


class ProviderFactoryTests(unittest.TestCase):
    def test_resolves_a_real_registered_data_provider(self) -> None:
        provider = ProviderFactory.get("local_demo")
        self.assertEqual(provider.provider_id, "local_demo")

    def test_resolves_a_real_registered_ai_provider(self) -> None:
        provider = ProviderFactory.get("null")
        self.assertEqual(provider.provider_id, "null")

    def test_returns_the_same_singleton_instance_every_call(self) -> None:
        """Providers are registered once, as singletons (unlike
        `ConnectorFactory.get()`, which instantiates a fresh connector per call) —
        two `ProviderFactory.get()` calls for the same id must return the identical
        object, not two equal-but-distinct ones.
        """
        self.assertIs(ProviderFactory.get("local_demo"), ProviderFactory.get("local_demo"))

    def test_raises_configuration_error_for_an_unknown_provider_id(self) -> None:
        with self.assertRaises(ProviderConfigurationError):
            ProviderFactory.get("not-a-real-provider")

    def test_delegates_to_the_registry_not_a_second_lookup_table(self) -> None:
        """`ProviderFactory` must not maintain any state of its own — registering a
        brand-new fake provider directly with `ProviderRegistry` should be
        immediately resolvable through `ProviderFactory` too, with no separate
        registration step.
        """
        from src.providers.base import Provider, ProviderKind
        from src.providers.registry import register_provider
        from src.providers.scoring import ProviderMetadata

        class _TempProvider(Provider):
            provider_id = "temp_factory_test_provider"
            kind = ProviderKind.DATA

            def is_available(self) -> bool:
                return True

            def metadata(self) -> ProviderMetadata:
                return ProviderMetadata(provider_id=self.provider_id, cost_score=0.0, freshness_score=0.0, quality_score=0.0)

        try:
            register_provider(_TempProvider())
            self.assertEqual(ProviderFactory.get("temp_factory_test_provider").provider_id, "temp_factory_test_provider")
        finally:
            ProviderRegistry._providers.pop("temp_factory_test_provider", None)


if __name__ == "__main__":
    unittest.main()
