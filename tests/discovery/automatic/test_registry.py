"""Tests for `DiscoveryProviderRegistry`/`DiscoveryProviderFactory` — mirrors
`tests/geography/test_registry.py`'s own shape. Confirms "adding a discovery
provider must require zero changes to AutomaticDiscoveryAgent" by registering a
brand-new, ad-hoc provider at test time and resolving it purely through the
registry/factory, with no agent code touched.
"""

from __future__ import annotations

import unittest

from src.discovery.automatic.base_provider import DiscoveryProvider
from src.discovery.automatic.exceptions import DiscoveryConfigurationError
from src.discovery.automatic.factory import DiscoveryProviderFactory
from src.discovery.automatic.metadata import DiscoveryProviderMetadata
from src.discovery.automatic.models import DiscoveredURL, DiscoveryRequest
from src.discovery.automatic.registry import DiscoveryProviderRegistry, register_discovery_provider


class _StubProvider(DiscoveryProvider):
    provider_id = "stub_test_provider"

    def metadata(self) -> DiscoveryProviderMetadata:
        return DiscoveryProviderMetadata(
            provider_id=self.provider_id, display_name="Stub", description="Test-only stub provider",
            source_type="test",
        )

    def discover(self, request: DiscoveryRequest) -> list[DiscoveredURL]:
        return [DiscoveredURL(url="https://stub.example.com", name="Stub Platform")]


class DiscoveryProviderRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previously_registered = dict(DiscoveryProviderRegistry._providers)

    def tearDown(self) -> None:
        DiscoveryProviderRegistry._providers = self._previously_registered

    def test_registering_a_brand_new_provider_requires_no_agent_changes(self) -> None:
        register_discovery_provider(_StubProvider())
        self.assertTrue(DiscoveryProviderRegistry.is_registered("stub_test_provider"))
        resolved = DiscoveryProviderFactory.get("stub_test_provider")
        self.assertIsInstance(resolved, _StubProvider)

    def test_registering_a_non_provider_instance_raises(self) -> None:
        with self.assertRaises(DiscoveryConfigurationError):
            register_discovery_provider(object())  # type: ignore[arg-type]

    def test_unknown_provider_id_raises_configuration_error(self) -> None:
        with self.assertRaises(DiscoveryConfigurationError):
            DiscoveryProviderFactory.get("does_not_exist")

    def test_resolve_none_returns_every_registered_provider(self) -> None:
        register_discovery_provider(_StubProvider())
        resolved = DiscoveryProviderFactory.resolve(None)
        self.assertIn("stub_test_provider", {p.provider_id for p in resolved})

    def test_resolve_explicit_list_returns_only_those_providers_in_order(self) -> None:
        register_discovery_provider(_StubProvider())
        resolved = DiscoveryProviderFactory.resolve(["stub_test_provider"])
        self.assertEqual([p.provider_id for p in resolved], ["stub_test_provider"])

    def test_builtin_curated_seed_and_manual_url_providers_are_registered(self) -> None:
        # Importing the package (already done at module load time elsewhere in the
        # suite) runs providers/__init__.py's self-registration side effect.
        import src.discovery.automatic  # noqa: F401

        self.assertTrue(DiscoveryProviderRegistry.is_registered("curated_seed"))
        self.assertTrue(DiscoveryProviderRegistry.is_registered("manual_url"))


if __name__ == "__main__":
    unittest.main()
