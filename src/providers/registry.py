"""Where every installed provider is known — see docs/21_Provider_Abstraction_Layer.md
"Registry". Deliberately simpler than `src.connectors.sdk.ConnectorRegistry`: connectors
are lazily imported per-platform on demand because which platform is needed isn't known
until a specific search targets it (`ConnectorFactory.get()`); every provider of a given
kind is a candidate on every routing decision, so there's no "which one do I need this
time" question to defer — the same reasoning `src.analysis.registry.AnalysisRegistry`
(v2.0 Step 6) already established for a small, known, eagerly-imported set. Providers
register **instances**, not classes: a provider has no per-search construction
parameters (unlike a connector, which takes a `ConnectorConfiguration`), so one shared
instance per provider is both correct and simpler than instantiating on every lookup.
"""

from __future__ import annotations

from src.providers.base import Provider, ProviderKind
from src.providers.exceptions import ProviderConfigurationError


class ProviderRegistry:
    """Class-level registry, not an instance — mirrors `ConnectorRegistry`/
    `AnalysisRegistry`: exactly one installed set of providers per process.
    """

    _providers: dict[str, Provider] = {}

    @classmethod
    def register(cls, provider: Provider) -> Provider:
        """Applied as `register_provider(SomeProvider())` directly under a provider
        class definition — runs at import time, which is what makes registration
        "self", not something `ProviderRouter` has to know to trigger.
        """
        if not isinstance(provider, Provider):
            raise ProviderConfigurationError(
                f"{provider!r} is not a Provider instance — register_provider() must "
                "be called with an instantiated Provider subclass"
            )
        if not getattr(provider, "provider_id", None):
            raise ProviderConfigurationError(
                f"{type(provider).__name__} must set a class-level `provider_id` "
                "before it can be registered"
            )
        cls._providers[provider.provider_id] = provider
        return provider

    @classmethod
    def get(cls, provider_id: str) -> Provider:
        try:
            return cls._providers[provider_id]
        except KeyError:
            raise ProviderConfigurationError(
                f"No provider registered for {provider_id!r}. Registered: "
                f"{sorted(cls._providers)}"
            ) from None

    @classmethod
    def all(cls, kind: ProviderKind | None = None) -> list[Provider]:
        """Every registered provider, optionally filtered to one `ProviderKind` —
        `ProviderRouter` always calls this with a kind; tests/introspection can omit it.
        """
        providers = list(cls._providers.values())
        return [provider for provider in providers if kind is None or provider.kind == kind]

    @classmethod
    def is_registered(cls, provider_id: str) -> bool:
        return provider_id in cls._providers

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered provider. Real code never calls this —
        providers self-register once, at import time, for the life of the process.
        """
        cls._providers.clear()


def register_provider(provider: Provider) -> Provider:
    """Module-level convenience matching `register_connector`'s call shape, adapted for
    instance registration: `register_provider(SomeProvider())` at the bottom of a
    provider module, instead of `@register_connector` decorating a class.
    """
    return ProviderRegistry.register(provider)
