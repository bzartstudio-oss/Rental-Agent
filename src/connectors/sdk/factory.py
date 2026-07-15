"""The only sanctioned way to get a connector instance — see
docs/18_Connector_SDK.md "Factory". `core/agent.py` must never construct a connector
class directly; every call site goes through `ConnectorFactory.get(platform)`.

Adding a new connector requires zero changes here: this factory only knows a
`Platform` row's own fields (`connector_available`, `connector_name`) and the registry
— never a specific platform's identity.
"""

from __future__ import annotations

from src.connectors.sdk.configuration import ConnectorConfiguration
from src.connectors.sdk.exceptions import ConnectorConfigurationError
from src.connectors.sdk.registry import ConnectorRegistry
from src.storage.models import Platform


class ConnectorFactory:
    @staticmethod
    def get(platform: Platform, config: ConnectorConfiguration | None = None):
        """Returns a ready-to-use `BaseConnector` instance for `platform`. Raises
        `ConnectorConfigurationError` — never a bare `KeyError`/`ImportError` — if the
        platform has no usable connector, so callers only ever need to catch one
        exception type (see docs/18_Connector_SDK.md "Error Handling").
        """
        if not platform.connector_available or not platform.connector_name:
            raise ConnectorConfigurationError(
                f"Platform {platform.id!r} has no available connector "
                f"(connector_available={platform.connector_available!r}, "
                f"connector_name={platform.connector_name!r})"
            )

        connector_class = ConnectorRegistry.get(platform.connector_name)
        return connector_class(config=config)
