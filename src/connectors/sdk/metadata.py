"""Declarative connector metadata and capability discovery — see
docs/18_Connector_SDK.md "Connector Metadata" / "Capability Discovery".

`ConnectorMetadata` is what one connector declares about itself (name, version,
coverage, which optional data it can supply) via `BaseConnector.connector_info()`.
`ConnectorCapabilities` is a thin, queryable view over that same data —
`BaseConnector.supports(...)` and `.capabilities()` both go through it, so "can this
platform give me coordinates?" is always one method call, never a manual field lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The named, first-class capability flags every connector declares up front on
# ConnectorMetadata. Anything not on this list (e.g. "price_history", "room_sharing")
# is still expressable via `extra_capabilities` — see ConnectorCapabilities.supports().
_NAMED_CAPABILITIES = (
    "images",
    "availability",
    "coordinates",
    "pagination",
    "incremental_search",
    "login",
)


@dataclass(frozen=True)
class ConnectorMetadata:
    """What a connector declares about itself — returned by
    `BaseConnector.connector_info()`, one instance per connector class (not per search).

    `rate_limit_per_minute=None` means "no known limit," not "unlimited" — same
    nullable-means-no-evidence-yet convention as the Knowledge Engine's rollup columns
    (docs/03_Data_Model.md). `extra_capabilities` is the open-ended escape hatch for a
    capability that doesn't warrant a named field yet (mission examples: "price_history",
    "room_sharing", "transport_information") — see `ConnectorCapabilities`.
    """

    connector_name: str
    platform_name: str
    version: str
    supported_countries: list[str] = field(default_factory=list)
    supported_cities: list[str] = field(default_factory=list)
    supported_rental_types: list[str] = field(default_factory=list)
    supported_languages: list[str] = field(default_factory=lambda: ["en"])
    supports_images: bool = False
    supports_availability: bool = False
    supports_coordinates: bool = False
    supports_pagination: bool = False
    supports_incremental_search: bool = False
    supports_login: bool = False
    rate_limit_per_minute: int | None = None
    extra_capabilities: dict[str, bool] = field(default_factory=dict)


class ConnectorCapabilities:
    """Capability discovery over one `ConnectorMetadata` instance —
    `BaseConnector.capabilities()` builds one of these from `connector_info()` on
    demand; `BaseConnector.supports(name)` delegates to `.supports(name)` here.
    """

    def __init__(self, metadata: ConnectorMetadata) -> None:
        self._metadata = metadata

    def supports_images(self) -> bool:
        return self._metadata.supports_images

    def supports_availability(self) -> bool:
        return self._metadata.supports_availability

    def supports_coordinates(self) -> bool:
        return self._metadata.supports_coordinates

    def supports_pagination(self) -> bool:
        return self._metadata.supports_pagination

    def supports_incremental_updates(self) -> bool:
        return self._metadata.supports_incremental_search

    def supports_login(self) -> bool:
        return self._metadata.supports_login

    def supports_price_history(self) -> bool:
        return self._metadata.extra_capabilities.get("price_history", False)

    def supports_room_sharing(self) -> bool:
        return self._metadata.extra_capabilities.get("room_sharing", False)

    def supports_transport_information(self) -> bool:
        return self._metadata.extra_capabilities.get("transport_information", False)

    def supports(self, capability: str) -> bool:
        """Generic lookup by name — e.g. `supports("images")` is equivalent to
        `supports_images()`. Falls back to `extra_capabilities` for anything without a
        named method, so a brand-new capability never needs a code change here first.
        """
        named_method = getattr(self, f"supports_{capability}", None)
        if callable(named_method):
            return named_method()
        return self._metadata.extra_capabilities.get(capability, False)

    def as_dict(self) -> dict[str, bool]:
        """Every named capability plus whatever's in `extra_capabilities` — useful for
        certification tests and `connector_info()` inspection without knowing every
        method name up front.
        """
        named = {name: self.supports(name) for name in _NAMED_CAPABILITIES}
        return {**named, **self._metadata.extra_capabilities}
