"""Importing this package runs every built-in discovery provider's
`register_discovery_provider(...)` call — mirrors `src.geography.providers`/
`src.feedback.rules`'s own self-registration-by-import shape.

The existing Platform Registry is deliberately NOT one of these providers: the
mission's own workflow checks it as a distinct first step ("Existing Platform
Registry -> determine refresh needed -> run selected providers -> ..."), and a
provider that queried it would need a live database connection at construction
time — which self-registered, eagerly-instantiated providers with zero per-call
parameters (registry.py's own rule) can't be given. `AutomaticDiscoveryAgent`
checks the registry directly via `src.discovery.platform_registry`.
"""

from __future__ import annotations

from src.discovery.automatic.providers import curated_seed_provider, manual_url_provider  # noqa: F401

__all__: list[str] = []
