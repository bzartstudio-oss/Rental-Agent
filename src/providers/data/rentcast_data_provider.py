"""`RentCastDataProvider` — the Provider-layer adapter over `RentCastConnector`
(v2.0 Step 7). See docs/21_Provider_Abstraction_Layer.md.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.connectors.sdk.factory import ConnectorFactory
from src.connectors.sdk.result import ConnectorResult
from src.providers.data.base_data_provider import DataProvider
from src.providers.registry import register_provider
from src.providers.scoring import ProviderMetadata
from src.search.search_request import SearchRequest
from src.storage.models import Platform

# A minimal, self-contained Platform row — this provider never needs the real
# `platforms` table row (which may or may not exist yet in a given database); all
# `ConnectorFactory.get()` actually reads off a Platform is `connector_available`/
# `connector_name`, both of which are fixed facts about RentCast, not data that needs
# to come from a lookup.
_PLATFORM = Platform(
    id="rentcast",
    name="RentCast",
    country="United States",
    homepage="https://www.rentcast.io",
    connector_available=True,
    connector_name="rentcast",
    created_at=datetime.now(timezone.utc),
)


class RentCastDataProvider(DataProvider):
    provider_id = "rentcast"
    platform_id = "rentcast"

    def is_available(self) -> bool:
        """Cheap, no-network check: does an API key exist to even attempt a call with?
        Whether that key is actually *valid* is discovered by `search()` itself, and is
        exactly the kind of failure `ProviderRouter.run_with_fallback()` falls back
        from — `is_available()` only rules out the case where trying at all would be
        pointless (no key configured whatsoever).
        """
        return bool(os.environ.get("RENTCAST_API_KEY"))

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            cost_score=0.2,
            freshness_score=0.9,
            quality_score=0.85,
            description="Real, live US rental listings via the RentCast API (see docs/20_First_Production_Connector.md)",
        )

    def search(self, request: SearchRequest) -> ConnectorResult:
        connector = ConnectorFactory.get(_PLATFORM)
        return connector.search(request)


register_provider(RentCastDataProvider())
