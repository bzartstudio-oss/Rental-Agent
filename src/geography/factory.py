"""`GeoProviderFactory` — the sanctioned way to resolve a geo provider by id,
mirroring `FilterFactory`/`ProviderFactory`'s same thin-delegation shape.
"""

from __future__ import annotations

from src.geography.base_provider import GeoProvider
from src.geography.registry import GeoProviderRegistry


class GeoProviderFactory:
    @staticmethod
    def get(provider_id: str) -> GeoProvider:
        """`GeoProviderRegistry.get()` already raises `GeoProviderConfigurationError`
        — never a bare `KeyError` — for an unknown id; this adds no logic of its own.
        """
        return GeoProviderRegistry.get(provider_id)

    @staticmethod
    def get_best_available() -> GeoProvider:
        """The first available registered provider — deterministic (registration
        order), not scored/ranked like `ProviderRouter` (there's currently exactly
        one built-in provider; this exists so a caller never needs to know its name).
        Raises `GeoProviderConfigurationError` if none are available.
        """
        from src.geography.exceptions import GeoProviderConfigurationError

        for provider in GeoProviderRegistry.all():
            if provider.is_available():
                return provider
        raise GeoProviderConfigurationError("no available geo provider is registered")
