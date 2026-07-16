"""`DiscoveryProviderMetadata` — a discovery provider's static self-description,
mirroring `FilterMetadata`/`GeoProviderMetadata`/`PreferenceRuleMetadata`'s same
declarative-capability-discovery role. See
docs/29_Automatic_Platform_Discovery.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryProviderMetadata:
    provider_id: str
    display_name: str
    description: str
    source_type: str  # e.g. "registry", "curated_seed", "manual_url", "web_search", "ai_assisted"
    requires_network_access: bool = False
