"""Unit tests for src/connectors/sdk/metadata.py — ConnectorMetadata + ConnectorCapabilities."""

import unittest

from src.connectors.sdk.metadata import ConnectorCapabilities, ConnectorMetadata


def _metadata(**overrides) -> ConnectorMetadata:
    defaults = dict(
        connector_name="test_connector",
        platform_name="Test Platform",
        version="1.0.0",
        supported_countries=["Testland"],
        supported_cities=["Test City"],
        supported_rental_types=["apartment"],
    )
    defaults.update(overrides)
    return ConnectorMetadata(**defaults)


class ConnectorMetadataTests(unittest.TestCase):
    def test_defaults_are_conservative(self) -> None:
        metadata = _metadata()

        self.assertFalse(metadata.supports_images)
        self.assertFalse(metadata.supports_availability)
        self.assertFalse(metadata.supports_coordinates)
        self.assertFalse(metadata.supports_pagination)
        self.assertFalse(metadata.supports_incremental_search)
        self.assertFalse(metadata.supports_login)
        self.assertIsNone(metadata.rate_limit_per_minute)
        self.assertEqual(metadata.supported_languages, ["en"])

    def test_is_immutable(self) -> None:
        metadata = _metadata()
        with self.assertRaises(Exception):
            metadata.version = "2.0.0"  # frozen dataclass


class ConnectorCapabilitiesTests(unittest.TestCase):
    def test_named_capabilities_reflect_metadata_flags(self) -> None:
        capabilities = ConnectorCapabilities(_metadata(supports_images=True, supports_coordinates=False))

        self.assertTrue(capabilities.supports_images())
        self.assertFalse(capabilities.supports_coordinates())

    def test_incremental_updates_maps_to_incremental_search_flag(self) -> None:
        capabilities = ConnectorCapabilities(_metadata(supports_incremental_search=True))
        self.assertTrue(capabilities.supports_incremental_updates())

    def test_extra_capabilities_default_to_false(self) -> None:
        capabilities = ConnectorCapabilities(_metadata())

        self.assertFalse(capabilities.supports_price_history())
        self.assertFalse(capabilities.supports_room_sharing())
        self.assertFalse(capabilities.supports_transport_information())

    def test_extra_capabilities_can_be_declared(self) -> None:
        capabilities = ConnectorCapabilities(_metadata(extra_capabilities={"price_history": True}))
        self.assertTrue(capabilities.supports_price_history())

    def test_generic_supports_lookup_matches_named_methods(self) -> None:
        capabilities = ConnectorCapabilities(_metadata(supports_images=True))

        self.assertTrue(capabilities.supports("images"))
        self.assertFalse(capabilities.supports("coordinates"))

    def test_generic_supports_lookup_falls_back_to_extra_capabilities(self) -> None:
        capabilities = ConnectorCapabilities(_metadata(extra_capabilities={"custom_thing": True}))
        self.assertTrue(capabilities.supports("custom_thing"))

    def test_unknown_capability_is_false_not_an_error(self) -> None:
        capabilities = ConnectorCapabilities(_metadata())
        self.assertFalse(capabilities.supports("something_nobody_declared"))

    def test_as_dict_includes_named_and_extra_capabilities(self) -> None:
        capabilities = ConnectorCapabilities(_metadata(supports_images=True, extra_capabilities={"room_sharing": True}))
        result = capabilities.as_dict()

        self.assertTrue(result["images"])
        self.assertFalse(result["coordinates"])
        self.assertTrue(result["room_sharing"])


if __name__ == "__main__":
    unittest.main()
