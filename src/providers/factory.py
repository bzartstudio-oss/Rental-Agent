"""`ProviderFactory` — the only sanctioned way to obtain a provider instance by name,
mirroring `src.connectors.sdk.factory.ConnectorFactory`'s role exactly. See
docs/24_Production_Providers.md "Provider Lifecycle".

Unlike `ConnectorFactory.get(platform, config)` (which *instantiates* a fresh
connector per call, since a connector takes a `ConnectorConfiguration` at
construction time), providers are registered once as singletons — see
`src.providers.registry`'s own docstring for why. `ProviderFactory.get(provider_id)`
therefore just resolves the already-registered instance; the layer of indirection
still matters, for the same reason it matters for connectors: a caller (`core/agent.py`,
`ProviderRouter`) never imports `src.providers.data.rentcast_data_provider` or any
other provider module directly, so a new provider is discoverable by every existing
caller without any of them changing.
"""

from __future__ import annotations

from src.providers.base import Provider
from src.providers.registry import ProviderRegistry


class ProviderFactory:
    @staticmethod
    def get(provider_id: str) -> Provider:
        """`ProviderRegistry.get()` already raises `ProviderConfigurationError` — never
        a bare `KeyError` — for an unknown `provider_id`; this method adds no logic of
        its own on top of it. It exists so callers depend on `ProviderFactory`, not
        `ProviderRegistry`, matching `ConnectorFactory`/`ConnectorRegistry`'s own
        split: the registry is where providers *live*, the factory is how callers
        *ask* for one — two different reasons to change, kept as two classes.
        """
        return ProviderRegistry.get(provider_id)
