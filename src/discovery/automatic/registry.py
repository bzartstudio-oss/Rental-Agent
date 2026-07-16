"""Where every installed discovery provider is known — mirrors `FeedbackRegistry`/
`RankingRuleRegistry`/`GeoProviderRegistry`'s self-registration + eager-import
shape. See docs/29_Automatic_Platform_Discovery.md "Discovery Providers" —
"Adding a discovery provider must require zero changes to AutomaticDiscoveryAgent"
is this registry's entire reason to exist.

Providers register **instances**, not classes — no built-in provider has any
per-call construction parameter, the same reasoning every prior plugin registry
in this codebase already applied to its own domain.
"""

from __future__ import annotations

from src.discovery.automatic.base_provider import DiscoveryProvider
from src.discovery.automatic.exceptions import DiscoveryConfigurationError


class DiscoveryProviderRegistry:
    _providers: dict[str, DiscoveryProvider] = {}

    @classmethod
    def register(cls, provider: DiscoveryProvider) -> DiscoveryProvider:
        if not isinstance(provider, DiscoveryProvider):
            raise DiscoveryConfigurationError(
                f"{provider!r} is not a DiscoveryProvider instance — register_discovery_provider() "
                "must be called with an instantiated DiscoveryProvider subclass"
            )
        if not getattr(provider, "provider_id", None):
            raise DiscoveryConfigurationError(
                f"{type(provider).__name__} must set a class-level `provider_id` before it can be registered"
            )
        cls._providers[provider.provider_id] = provider
        return provider

    @classmethod
    def get(cls, provider_id: str) -> DiscoveryProvider:
        try:
            return cls._providers[provider_id]
        except KeyError:
            raise DiscoveryConfigurationError(
                f"No discovery provider registered for {provider_id!r}. Registered: {sorted(cls._providers)}"
            ) from None

    @classmethod
    def all(cls) -> list[DiscoveryProvider]:
        return list(cls._providers.values())

    @classmethod
    def is_registered(cls, provider_id: str) -> bool:
        return provider_id in cls._providers

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered discovery provider. Real code never calls this."""
        cls._providers.clear()


def register_discovery_provider(provider: DiscoveryProvider) -> DiscoveryProvider:
    return DiscoveryProviderRegistry.register(provider)
