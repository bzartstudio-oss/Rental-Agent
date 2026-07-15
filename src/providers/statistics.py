"""`ProviderStatistics` — the aggregate, multi-run view of a provider's reliability,
distinct from `ProviderMetrics` (one run) and `ProviderHealth` (current point-in-time
state). See docs/24_Production_Providers.md "Metrics".

Reuses `src.knowledge.knowledge_service.platform_statistics()` (v2.0 Step 4) —
`PlatformKnowledge` already *is* "provider statistics" for anything backed by a real
platform; this module doesn't recompute reliability/success-rate/duplicate-rate
formulas, it looks them up under the provider's `platform_id` and re-shapes the
result under a provider-scoped name.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from src.knowledge import knowledge_service
from src.knowledge.models import PlatformKnowledge
from src.providers.base import Provider


@dataclass
class ProviderStatistics:
    provider_id: str
    platform_id: str | None
    platform_knowledge: PlatformKnowledge | None


def provider_statistics(provider: Provider, conn: sqlite3.Connection) -> ProviderStatistics:
    """`platform_knowledge=None` for an `AIProvider` (no `platform_id`, nothing to look
    up) or for a `DataProvider` whose platform has zero observations yet — both are
    honest "no evidence yet," never a fabricated zero, matching
    `knowledge_service.platform_statistics()`'s own nullable-rollup convention.
    """
    platform_id = getattr(provider, "platform_id", None)
    if platform_id is None:
        return ProviderStatistics(provider_id=provider.provider_id, platform_id=None, platform_knowledge=None)

    try:
        knowledge = knowledge_service.platform_reliability(conn, platform_id)
    except KeyError:
        # The platform isn't registered in `platforms` at all yet — same honest
        # degradation as ProviderHealth's "no observations" case, not an error.
        return ProviderStatistics(provider_id=provider.provider_id, platform_id=platform_id, platform_knowledge=None)

    return ProviderStatistics(provider_id=provider.provider_id, platform_id=platform_id, platform_knowledge=knowledge)
