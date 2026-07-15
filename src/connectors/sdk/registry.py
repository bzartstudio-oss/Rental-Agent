"""Where every installed connector is known — see docs/18_Connector_SDK.md "Registry".

A connector self-registers by decorating its class with `@register_connector`; the
registry itself never imports a specific connector module by name (that would mean
editing this file for every new platform, exactly what the mission says a new
connector must not require). `ConnectorFactory` triggers the import (by the
`src.connectors.<connector_name>` naming convention already established in v1.1) and
then asks the registry for the now-registered class.
"""

from __future__ import annotations

import importlib

from src.connectors.sdk.exceptions import ConnectorConfigurationError


class ConnectorRegistry:
    """Class-level registry, not an instance — there is exactly one installed set of
    connectors per process, the same way there's exactly one `platforms` table.
    """

    _connectors: dict[str, type] = {}

    @classmethod
    def register(cls, connector_class: type) -> type:
        """Applied as `@register_connector` (see below) directly under a connector
        class definition — runs at import time, which is what makes registration
        "self", not something `ConnectorFactory`/this registry has to know to do.
        """
        platform_id = getattr(connector_class, "platform_id", None)
        if not platform_id:
            raise ConnectorConfigurationError(
                f"{connector_class.__name__} must set a class-level `platform_id` "
                "before it can be registered"
            )
        cls._connectors[platform_id] = connector_class
        return connector_class

    @classmethod
    def get(cls, connector_name: str) -> type:
        """Returns the registered connector class for `connector_name`, importing
        `src.connectors.<connector_name>` first if it hasn't been loaded yet — that
        import is what triggers the module's own `@register_connector` decorator.
        """
        if connector_name not in cls._connectors:
            cls._ensure_imported(connector_name)

        try:
            return cls._connectors[connector_name]
        except KeyError:
            raise ConnectorConfigurationError(
                f"No connector registered for {connector_name!r} — its module was "
                "imported but never called @register_connector on a matching "
                f"platform_id={connector_name!r} class"
            ) from None

    @classmethod
    def is_registered(cls, connector_name: str) -> bool:
        return connector_name in cls._connectors

    @classmethod
    def all(cls) -> list[type]:
        """Every connector class registered so far *in this process* — not "every
        connector that could ever exist," since one that's never been imported hasn't
        run its `@register_connector` decorator yet. Sufficient for introspection/
        certification tooling; not used by the search path (`ConnectorFactory.get`
        imports on demand instead, so a search never depends on import order).
        """
        return list(cls._connectors.values())

    @classmethod
    def _ensure_imported(cls, connector_name: str) -> None:
        module_name = f"src.connectors.{connector_name}"
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise ConnectorConfigurationError(
                f"No connector module found for {connector_name!r} (looked for "
                f"{module_name}): {exc}"
            ) from exc


def register_connector(connector_class: type) -> type:
    """Decorator form of `ConnectorRegistry.register` — put `@register_connector`
    directly above a `BaseConnector` subclass, same place `CONNECTOR = <Subclass>`
    used to go under demo_platform.py/demo_platform_two.py before this SDK existed.
    """
    return ConnectorRegistry.register(connector_class)
