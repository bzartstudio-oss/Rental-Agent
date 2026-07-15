"""`GeoProviderMetadata` — a geo provider's static self-description, mirroring
`ConnectorMetadata`/`ProviderMetadata`'s same declarative-capability-discovery role.
See docs/26_Geographic_Intelligence.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GeoProviderMetadata:
    provider_id: str
    display_name: str
    supports_real_routing: bool  # False for a straight-line/estimate-based provider
    supported_modes: list[str] = field(default_factory=list)
    supported_nearby_categories: list[str] = field(default_factory=list)
    description: str = ""
