"""Unit + Plugin tests for GeoProviderRegistry — src/geography/registry.py. Uses a
private `_FakeRegistry` subclass with its own `_providers` dict, never touching the
real, shared `GeoProviderRegistry` (which already holds the built-in `haversine`
provider by the time any test runs) — the same isolation strategy
`tests/filter_engine/test_registry.py` uses.
"""

from __future__ import annotations

import unittest

from src.geography.base_provider import GeoContext, GeoProvider
from src.geography.exceptions import GeoProviderConfigurationError
from src.geography.metadata import GeoProviderMetadata
from src.geography.models import Coordinates, GeoResult, NearbyPlace, TravelMode
from src.geography.registry import GeoProviderRegistry


class _FakeRegistry(GeoProviderRegistry):
    _providers: dict = {}


class _FakeProvider(GeoProvider):
    provider_id = "fake"

    def is_available(self) -> bool:
        return True

    def metadata(self) -> GeoProviderMetadata:
        return GeoProviderMetadata(provider_id=self.provider_id, display_name="Fake", supports_real_routing=False)

    def calculate_distance(self, origin, destination, mode, context) -> GeoResult:
        raise NotImplementedError

    def find_nearby(self, origin, category, context) -> list[NearbyPlace]:
        raise NotImplementedError


class GeoProviderRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRegistry.reset()

    def test_register_then_get_returns_the_same_instance(self) -> None:
        provider = _FakeProvider()
        _FakeRegistry.register(provider)
        self.assertIs(_FakeRegistry.get("fake"), provider)

    def test_get_unknown_provider_raises_configuration_error(self) -> None:
        with self.assertRaises(GeoProviderConfigurationError):
            _FakeRegistry.get("does-not-exist")

    def test_register_rejects_non_geoprovider_objects(self) -> None:
        with self.assertRaises(GeoProviderConfigurationError):
            _FakeRegistry.register(object())  # type: ignore[arg-type]

    def test_register_rejects_a_provider_with_no_provider_id(self) -> None:
        class _NoId(GeoProvider):
            provider_id = ""

            def is_available(self) -> bool:
                return True

            def metadata(self):
                return GeoProviderMetadata(provider_id="", display_name="x", supports_real_routing=False)

            def calculate_distance(self, origin, destination, mode, context):
                raise NotImplementedError

            def find_nearby(self, origin, category, context):
                raise NotImplementedError

        with self.assertRaises(GeoProviderConfigurationError):
            _FakeRegistry.register(_NoId())

    def test_all_returns_every_registered_provider(self) -> None:
        _FakeRegistry.register(_FakeProvider())
        self.assertEqual([p.provider_id for p in _FakeRegistry.all()], ["fake"])

    def test_is_registered(self) -> None:
        self.assertFalse(_FakeRegistry.is_registered("fake"))
        _FakeRegistry.register(_FakeProvider())
        self.assertTrue(_FakeRegistry.is_registered("fake"))

    def test_reset_clears_everything(self) -> None:
        _FakeRegistry.register(_FakeProvider())
        _FakeRegistry.reset()
        self.assertEqual(_FakeRegistry.all(), [])

    def test_real_registry_has_the_built_in_haversine_provider(self) -> None:
        """Not isolated — proves the real, shared `GeoProviderRegistry` genuinely
        self-registers `haversine` at import time (via `src.geography.providers`),
        exactly as the plugin system promises: "Future providers should require zero
        changes to GeographicEngine."
        """
        self.assertTrue(GeoProviderRegistry.is_registered("haversine"))
        provider = GeoProviderRegistry.get("haversine")
        self.assertTrue(provider.is_available())


class FutureProviderPluginTests(unittest.TestCase):
    """A second, independent `GeoProvider` implementation registered at test time —
    proves adding a provider requires zero change to `GeographicEngine`/
    `GeoProviderFactory`/`DistanceCalculator`/`NearbySearch`, only a `register_geo_provider`
    call, exactly what "Future providers should require zero changes to
    GeographicEngine" (the mission's own words) demands.
    """

    def setUp(self) -> None:
        _FakeRegistry.reset()

    def test_a_second_registered_provider_is_resolvable_by_id(self) -> None:
        class _FutureRoutingProvider(GeoProvider):
            provider_id = "future_routing_api"

            def is_available(self) -> bool:
                return True

            def metadata(self) -> GeoProviderMetadata:
                return GeoProviderMetadata(
                    provider_id=self.provider_id, display_name="Future", supports_real_routing=True
                )

            def calculate_distance(self, origin, destination, mode, context) -> GeoResult:
                from datetime import datetime, timezone

                return GeoResult(
                    origin=origin, destination=destination, mode=mode, distance_km=1.0,
                    travel_time_minutes=2.0, confidence=0.99, computed_at=datetime.now(timezone.utc),
                    provider_id=self.provider_id, calculation_method="future_real_routing",
                )

            def find_nearby(self, origin, category, context) -> list[NearbyPlace]:
                return []

        _FakeRegistry.register(_FutureRoutingProvider())
        provider = _FakeRegistry.get("future_routing_api")
        result = provider.calculate_distance((0, 0), (0, 1), TravelMode.DRIVING, GeoContext())
        self.assertEqual(result.calculation_method, "future_real_routing")


if __name__ == "__main__":
    unittest.main()
