"""Unit tests for src/connectors/sdk/factory.py — ConnectorFactory.

"The Research Agent must never instantiate connectors directly" is the property these
tests exist to protect: everything needed to get a working connector must be reachable
through `ConnectorFactory.get(platform)` alone, given just a `Platform` row.
"""

import unittest
from datetime import datetime, timezone

from src.connectors.demo_platform import DemoPlatformConnector
from src.connectors.sdk.configuration import ConnectorConfiguration
from src.connectors.sdk.exceptions import ConnectorConfigurationError
from src.connectors.sdk.factory import ConnectorFactory
from src.storage.models import Platform


def _platform(**overrides) -> Platform:
    defaults = dict(
        id="demo_platform",
        name="Demo Platform",
        country="N/A",
        homepage="local-fixture",
        connector_available=True,
        connector_name="demo_platform",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Platform(**defaults)


class ConnectorFactoryTests(unittest.TestCase):
    def test_returns_a_ready_to_use_connector_instance(self) -> None:
        connector = ConnectorFactory.get(_platform())
        self.assertIsInstance(connector, DemoPlatformConnector)

    def test_passes_through_a_given_configuration(self) -> None:
        config = ConnectorConfiguration(headless=False, timeout_ms=5000)
        connector = ConnectorFactory.get(_platform(), config=config)
        self.assertIs(connector.config, config)

    def test_uses_default_configuration_when_none_given(self) -> None:
        connector = ConnectorFactory.get(_platform())
        self.assertIsInstance(connector.config, ConnectorConfiguration)

    def test_raises_for_a_platform_with_connector_available_false(self) -> None:
        with self.assertRaises(ConnectorConfigurationError):
            ConnectorFactory.get(_platform(connector_available=False, connector_name=None))

    def test_raises_for_a_platform_with_no_connector_name(self) -> None:
        with self.assertRaises(ConnectorConfigurationError):
            ConnectorFactory.get(_platform(connector_name=None))

    def test_raises_for_an_unresolvable_connector_module(self) -> None:
        with self.assertRaises(ConnectorConfigurationError):
            ConnectorFactory.get(_platform(id="ghost", connector_name="does_not_exist_module"))


if __name__ == "__main__":
    unittest.main()
