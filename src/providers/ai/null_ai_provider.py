"""`NullAIProvider` — the guaranteed-always-available AI provider: honestly produces no
summary rather than fabricating one. Ensures `ProviderRouter(ProviderKind.AI)` always
has at least one usable candidate, mirroring `LocalDemoDataProvider`'s role for data
providers. See docs/21_Provider_Abstraction_Layer.md.
"""

from __future__ import annotations

from src.providers.ai.base_ai_provider import AIProvider
from src.providers.configuration import ProviderConfiguration
from src.providers.registry import register_provider
from src.providers.scoring import ProviderMetadata
from src.ranking.ranking_engine import RankedApartment
from src.search.search_request import SearchRequest


class NullAIProvider(AIProvider):
    provider_id = "null"

    def is_available(self) -> bool:
        return True

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            cost_score=0.0,
            freshness_score=1.0,
            # Deliberately the lowest possible quality score — any real AI provider
            # that's actually available should always outrank this one; it exists
            # purely as a guaranteed, honest fallback, never a first choice.
            quality_score=0.0,
            description="No-op AI provider — always available, never fabricates a summary",
        )

    def summarize(
        self,
        ranked: list[RankedApartment],
        request: SearchRequest,
        config: ProviderConfiguration | None = None,
    ) -> str | None:
        return None


register_provider(NullAIProvider())
