"""`CuratedSeedDiscoveryProvider` — surfaces platforms already recorded in
`src.discovery.known_platforms` (public, well-known rental-platform facts,
hand-compiled without visiting any live site — see that module's own docstring)
as discovery candidates for a request's country. See
docs/29_Automatic_Platform_Discovery.md "Discovery Providers".

Deliberately reuses `known_platforms.ALL_KNOWN_PLATFORMS` rather than a second,
duplicate seed list — the same "reuse over duplication" discipline this codebase
applies everywhere else. Local fixture entries (`demo_platform`/`demo_platform_two`,
whose `homepage` is a fixture marker, not a real URL) are excluded — surfacing them
as "discovered" would misrepresent a test fixture as a real rental platform.
"""

from __future__ import annotations

from src.discovery.automatic.base_provider import DiscoveryProvider
from src.discovery.automatic.metadata import DiscoveryProviderMetadata
from src.discovery.automatic.models import DiscoveredURL, DiscoveryRequest
from src.discovery.automatic.registry import register_discovery_provider
from src.discovery.known_platforms import ALL_KNOWN_PLATFORMS


class CuratedSeedDiscoveryProvider(DiscoveryProvider):
    provider_id = "curated_seed"

    def metadata(self) -> DiscoveryProviderMetadata:
        return DiscoveryProviderMetadata(
            provider_id=self.provider_id,
            display_name="Curated Seed List (known_platforms.py)",
            description=(
                "Public, hand-compiled facts about well-known rental platforms — no live "
                "request made to any of them. Filtered by the request's country when given."
            ),
            source_type="curated_seed",
            requires_network_access=False,
        )

    def discover(self, request: DiscoveryRequest) -> list[DiscoveredURL]:
        results = []
        for candidate in ALL_KNOWN_PLATFORMS:
            if not candidate.homepage.startswith("http"):
                continue  # local fixture, not a real URL
            if request.country and candidate.country.lower() != request.country.lower():
                continue
            results.append(
                DiscoveredURL(
                    url=candidate.homepage,
                    name=candidate.name,
                    source_hint=f"curated_seed:{candidate.discovery_method}",
                    metadata={
                        "country": candidate.country,
                        "supported_cities": candidate.supported_cities,
                        "rental_types": candidate.rental_types,
                        "requires_login": candidate.requires_login,
                        "connector_available": candidate.connector_available,
                        "connector_name": candidate.connector_name,
                        "notes": candidate.notes,
                    },
                )
            )
        return results


register_discovery_provider(CuratedSeedDiscoveryProvider())
