"""Unit tests for src/connectors/sdk/registry.py — ConnectorRegistry + register_connector.

Uses a throwaway `platform_id` and manually removes it in tearDown, since the registry
is a class-level (process-wide) dict — tests must not leak state that could affect the
real connectors (`demo_platform`, `demo_platform_two`) registered elsewhere.
"""

import unittest

from src.connectors.sdk.base_connector import BaseConnector
from src.connectors.sdk.exceptions import ConnectorConfigurationError
from src.connectors.sdk.metadata import ConnectorMetadata
from src.connectors.sdk.registry import ConnectorRegistry, register_connector


class _FakeConnector(BaseConnector):
    platform_id = "test_registry_fake_connector"

    def build_url(self, request):
        return "https://example.com"

    def parse(self, raw_response):
        return []

    def normalize(self, raw_record):
        raise NotImplementedError

    def connector_info(self) -> ConnectorMetadata:
        return ConnectorMetadata(connector_name=self.platform_id, platform_name="Fake", version="1.0.0")


class ConnectorRegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        ConnectorRegistry._connectors.pop("test_registry_fake_connector", None)
        ConnectorRegistry._connectors.pop("test_registry_undecorated", None)

    def test_register_connector_decorator_registers_the_class(self) -> None:
        register_connector(_FakeConnector)
        self.assertTrue(ConnectorRegistry.is_registered("test_registry_fake_connector"))
        self.assertIs(ConnectorRegistry.get("test_registry_fake_connector"), _FakeConnector)

    def test_register_requires_a_platform_id(self) -> None:
        class _NoPlatformId(BaseConnector):
            def build_url(self, request):
                return ""

            def parse(self, raw_response):
                return []

            def normalize(self, raw_record):
                raise NotImplementedError

            def connector_info(self):
                raise NotImplementedError

        with self.assertRaises(ConnectorConfigurationError):
            ConnectorRegistry.register(_NoPlatformId)

    def test_get_raises_for_a_connector_with_no_matching_module(self) -> None:
        with self.assertRaises(ConnectorConfigurationError):
            ConnectorRegistry.get("this_module_does_not_exist_anywhere")

    def test_is_registered_is_false_for_unknown_connectors(self) -> None:
        self.assertFalse(ConnectorRegistry.is_registered("something_never_registered"))

    def test_demo_platform_is_registered_by_importing_its_module(self) -> None:
        """The real self-registration path: importing the module (not calling
        register_connector by hand) is what makes ConnectorRegistry.get() work —
        exactly what ConnectorFactory relies on.
        """
        connector_class = ConnectorRegistry.get("demo_platform")
        self.assertEqual(connector_class.platform_id, "demo_platform")

    def test_all_returns_every_registered_connector_class(self) -> None:
        register_connector(_FakeConnector)
        self.assertIn(_FakeConnector, ConnectorRegistry.all())


if __name__ == "__main__":
    unittest.main()
