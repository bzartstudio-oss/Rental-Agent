"""Where every installed geo provider is known — mirrors `FilterRegistry`/
`ProviderRegistry`'s self-registration + eager-import shape (a small, known set of
providers, all always candidates). See docs/26_Geographic_Intelligence.md
"Plugin System".

Providers register **instances**, not classes — no built-in geo provider has any
per-call construction parameter, so one shared instance per provider, registered
once at import time, is correct and simpler than a per-instantiation model.
"""

from __future__ import annotations

from src.geography.base_provider import GeoProvider
from src.geography.exceptions import GeoProviderConfigurationError


class GeoProviderRegistry:
    _providers: dict[str, GeoProvider] = {}

    @classmethod
    def register(cls, provider: GeoProvider) -> GeoProvider:
        if not isinstance(provider, GeoProvider):
            raise GeoProviderConfigurationError(
                f"{provider!r} is not a GeoProvider instance — register_geo_provider() "
                "must be called with an instantiated GeoProvider subclass"
            )
        if not getattr(provider, "provider_id", None):
            raise GeoProviderConfigurationError(
                f"{type(provider).__name__} must set a class-level `provider_id` "
                "before it can be registered"
            )
        cls._providers[provider.provider_id] = provider
        return provider

    @classmethod
    def get(cls, provider_id: str) -> GeoProvider:
        try:
            return cls._providers[provider_id]
        except KeyError:
            raise GeoProviderConfigurationError(
                f"No geo provider registered for {provider_id!r}. Registered: {sorted(cls._providers)}"
            ) from None

    @classmethod
    def all(cls) -> list[GeoProvider]:
        return list(cls._providers.values())

    @classmethod
    def is_registered(cls, provider_id: str) -> bool:
        return provider_id in cls._providers

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered geo provider. Real code never calls this."""
        cls._providers.clear()


def register_geo_provider(provider: GeoProvider) -> GeoProvider:
    return GeoProviderRegistry.register(provider)
