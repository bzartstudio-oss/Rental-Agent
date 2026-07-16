"""`DiscoveryProvider` — the plugin contract every discovery source implements. See
docs/29_Automatic_Platform_Discovery.md "Discovery Providers".

Deliberately provider-agnostic: nothing here assumes a specific search engine, a
specific seed list format, or any specific vendor API. "Do not hardcode one search
engine" (the mission's own words) — a future real web-search-API provider or
AI-assisted classification provider implements this same interface;
`AutomaticDiscoveryAgent`/`DiscoveryProviderRegistry` require zero changes when one
is added, the same "prepare interfaces for future integrations" guarantee every
prior plugin system in this codebase already proved for its own domain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.discovery.automatic.metadata import DiscoveryProviderMetadata
from src.discovery.automatic.models import DiscoveredURL, DiscoveryRequest


class DiscoveryProvider(ABC):
    provider_id: str

    @abstractmethod
    def metadata(self) -> DiscoveryProviderMetadata:
        raise NotImplementedError

    @abstractmethod
    def discover(self, request: DiscoveryRequest) -> list[DiscoveredURL]:
        """Returns every candidate URL this provider found for `request`. An empty
        list is an honest "nothing found," never fabricated. Raises
        `DiscoveryProviderError` (never a bare exception) only for a genuine
        execution failure — a network error, a misconfigured provider — which the
        pipeline records as a failed `DiscoveryProviderObservation` and continues
        with whatever other providers succeeded, the same "one broken source
        can't take down the whole run" resilience `RentalResearchAgent.run()`
        already gives individual connectors.
        """
        raise NotImplementedError
