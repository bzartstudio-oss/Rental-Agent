"""`ProviderHealth` — a provider's current, point-in-time health: is it available
right now, and (for a data provider backed by a real platform) what does its
historical `ConnectorHealth` say. See docs/24_Production_Providers.md "Provider
Health".

Deliberately does NOT redefine or recompute anything the Knowledge Engine already
tracks — `ConnectorHealth` (`src.knowledge.models`, reused by `BaseConnector.
health_check()` since v2.0 Step 5) is reused here exactly as-is. The only genuinely
new fact `ProviderHealth` adds on top of it is `is_available_now`: a live
`Provider.is_available()` call, which `ConnectorHealth` has no notion of (a connector
doesn't have an "is configured right now" concept the way a provider does — a
provider's own `is_available()` is what `ProviderRouter` gates candidacy on).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from src.knowledge import knowledge_service
from src.knowledge.models import ConnectorHealth
from src.providers.base import Provider


@dataclass
class ProviderHealth:
    provider_id: str
    is_available_now: bool
    platform_id: str | None
    connector_health: ConnectorHealth | None


def check_provider_health(provider: Provider, conn: sqlite3.Connection) -> ProviderHealth:
    """`platform_id` is read via `getattr` rather than an `isinstance(provider,
    DataProvider)` check — this module has no reason to import `providers.data` at
    all, and an `AIProvider` (no `platform_id` attribute, no row in `platforms`)
    should degrade to `platform_id=None`/`connector_health=None` just as gracefully as
    a `DataProvider` whose platform has no observations yet (`connector_health` is
    `None` in both cases, never a fabricated "no data" object).
    """
    platform_id = getattr(provider, "platform_id", None)
    connector_health: ConnectorHealth | None = None

    if platform_id is not None:
        results = knowledge_service.connector_health(conn, platform_id=platform_id)
        connector_health = results[0] if results else None

    return ProviderHealth(
        provider_id=provider.provider_id,
        is_available_now=provider.is_available(),
        platform_id=platform_id,
        connector_health=connector_health,
    )
