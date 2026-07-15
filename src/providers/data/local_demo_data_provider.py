"""`LocalDemoDataProvider` — the guaranteed-always-available data provider, so the
whole system works with zero configuration. Wraps `DemoPlatformConnector` (v2.0 Step 5),
a real Playwright fetch of a real local HTML fixture — see
docs/21_Provider_Abstraction_Layer.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.connectors.sdk.configuration import ConnectorConfiguration
from src.connectors.sdk.factory import ConnectorFactory
from src.connectors.sdk.result import ConnectorResult
from src.providers.configuration import ProviderConfiguration
from src.providers.data.base_data_provider import DataProvider
from src.providers.registry import register_provider
from src.providers.scoring import ProviderMetadata
from src.search.search_request import SearchRequest
from src.storage.models import Platform

_PLATFORM = Platform(
    id="demo_platform",
    name="Demo Platform (reference/demo connector, not real)",
    country="N/A (local fixture)",
    homepage="local-fixture",
    connector_available=True,
    connector_name="demo_platform",
    created_at=datetime.now(timezone.utc),
)


class LocalDemoDataProvider(DataProvider):
    provider_id = "local_demo"
    platform_id = "demo_platform"

    def is_available(self) -> bool:
        """Always available — no external service, no credential, no network
        dependency beyond the local Playwright/Chromium install every connector
        already requires. This is what makes "the first version works without any API
        key" literally true: when RentCast is unavailable (no key) or fails, this is
        always left in `ranked_candidates()`.
        """
        return True

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            cost_score=0.0,
            freshness_score=0.1,
            quality_score=0.3,
            description="Local fixture-backed demo connector — always available, no external dependency, not real listings",
        )

    def search(self, request: SearchRequest, config: ProviderConfiguration | None = None) -> ConnectorResult:
        connector_config = (
            ConnectorConfiguration(timeout_ms=config.timeout_ms, max_retries=config.max_retries)
            if config is not None
            else None
        )
        connector = ConnectorFactory.get(_PLATFORM, config=connector_config)
        return connector.search(request)


register_provider(LocalDemoDataProvider())
