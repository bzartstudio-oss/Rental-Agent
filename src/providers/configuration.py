"""Per-provider runtime configuration — mirrors
`src.connectors.sdk.configuration.ConnectorConfiguration` deliberately: a provider's
job is choosing *which* connector-backed source to use, and a caller configuring that
choice (timeout, retries, credentials) should look and feel identical to configuring
the connector underneath it, not invent a second configuration vocabulary. See
docs/24_Production_Providers.md "Provider Lifecycle".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfiguration:
    """Passed into `DataProvider.search()`/`AIProvider.summarize()` (both default this
    to `None` — every existing call site, including `ProviderRouter.run_with_fallback()`
    lambdas written before this sprint, keeps working unchanged). A `DataProvider`
    translates this into a `ConnectorConfiguration` at the one point it calls
    `ConnectorFactory.get()` — the values are never re-implemented, just carried
    through to the mechanism that already understands them.
    """

    timeout_ms: int = 30_000
    max_retries: int = 0
    rate_limit_per_minute: int | None = None
    credentials: dict[str, str] | None = None
