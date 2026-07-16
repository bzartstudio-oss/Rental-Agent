"""`DiscoveryProviderFactory` — the sanctioned way to resolve a discovery provider
by id, mirroring `FeedbackRegistry`/`RankingRuleRegistry`'s sibling factories'
same thin-delegation shape.
"""

from __future__ import annotations

from src.discovery.automatic.base_provider import DiscoveryProvider
from src.discovery.automatic.registry import DiscoveryProviderRegistry


class DiscoveryProviderFactory:
    @staticmethod
    def get(provider_id: str) -> DiscoveryProvider:
        """`DiscoveryProviderRegistry.get()` already raises `DiscoveryConfigurationError`
        — never a bare `KeyError` — for an unknown id; this adds no logic of its own.
        """
        return DiscoveryProviderRegistry.get(provider_id)

    @staticmethod
    def resolve(provider_ids: list[str] | None) -> list[DiscoveryProvider]:
        """`None` (the default) resolves to every registered provider; an explicit
        list resolves to exactly those, in the order given — "discovery provider
        selection" (the mission's own `DiscoveryRequest` field).
        """
        if provider_ids is None:
            return DiscoveryProviderRegistry.all()
        return [DiscoveryProviderFactory.get(provider_id) for provider_id in provider_ids]
