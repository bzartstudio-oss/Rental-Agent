"""`ManualUrlDiscoveryProvider` — turns a request's own `manual_urls` into
discovery candidates, so a manually-supplied URL flows through the exact same
normalization/evidence/classification/verification pipeline as anything found
by another provider, rather than needing a special-cased code path. See
docs/29_Automatic_Platform_Discovery.md "Discovery Providers".
"""

from __future__ import annotations

from src.discovery.automatic.base_provider import DiscoveryProvider
from src.discovery.automatic.metadata import DiscoveryProviderMetadata
from src.discovery.automatic.models import DiscoveredURL, DiscoveryRequest
from src.discovery.automatic.registry import register_discovery_provider


class ManualUrlDiscoveryProvider(DiscoveryProvider):
    provider_id = "manual_url"

    def metadata(self) -> DiscoveryProviderMetadata:
        return DiscoveryProviderMetadata(
            provider_id=self.provider_id,
            display_name="Manual URLs",
            description="URLs the caller supplied directly on the DiscoveryRequest itself.",
            source_type="manual_url",
            requires_network_access=False,
        )

    def discover(self, request: DiscoveryRequest) -> list[DiscoveredURL]:
        return [DiscoveredURL(url=url, name=None, source_hint="manual_url") for url in request.manual_urls]


register_discovery_provider(ManualUrlDiscoveryProvider())
