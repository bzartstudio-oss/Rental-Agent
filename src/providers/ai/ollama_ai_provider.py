"""`OllamaAIProvider` — summarization/enrichment via a local Ollama server
(https://ollama.com), entirely optional: nothing in this codebase requires Ollama to
be installed or running. See docs/21_Provider_Abstraction_Layer.md.
"""

from __future__ import annotations

import os

import requests

from src.providers.ai.base_ai_provider import AIProvider
from src.providers.configuration import ProviderConfiguration
from src.providers.exceptions import ProviderException
from src.providers.registry import register_provider
from src.providers.scoring import ProviderMetadata
from src.ranking.ranking_engine import RankedApartment
from src.search.search_request import SearchRequest

_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
_AVAILABILITY_TIMEOUT_S = 1.5
_GENERATE_TIMEOUT_S = 30.0


class OllamaAIProviderError(ProviderException):
    """Ollama was available at routing time but the actual summarize() call failed —
    caught by `ProviderRouter.run_with_fallback()`, which then tries the next AI
    provider (typically `NullAIProvider`), never propagated to the caller.
    """


class OllamaAIProvider(AIProvider):
    provider_id = "ollama"

    def is_available(self) -> bool:
        """A real reachability check (`GET /api/tags`, Ollama's own list-models
        endpoint), not just "is an environment variable set" — unlike an API key,
        there's no cheaper signal for "is a local server actually up." Kept to a short
        timeout so an absent Ollama install doesn't add real latency to every routing
        decision; any exception (connection refused, timeout) means unavailable, never
        a crash.
        """
        try:
            response = requests.get(f"{_BASE_URL}/api/tags", timeout=_AVAILABILITY_TIMEOUT_S)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            cost_score=0.0,
            freshness_score=1.0,
            quality_score=0.6,
            description=f"Local Ollama LLM ({_MODEL}) for search-result summarization",
        )

    def summarize(
        self,
        ranked: list[RankedApartment],
        request: SearchRequest,
        config: ProviderConfiguration | None = None,
    ) -> str | None:
        prompt = _build_prompt(ranked, request)
        timeout_s = config.timeout_ms / 1000 if config is not None else _GENERATE_TIMEOUT_S
        try:
            response = requests.post(
                f"{_BASE_URL}/api/generate",
                json={"model": _MODEL, "prompt": prompt, "stream": False},
                timeout=timeout_s,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaAIProviderError(f"ollama: request failed: {exc}") from exc

        text = (response.json().get("response") or "").strip()
        return text or None


def _build_prompt(ranked: list[RankedApartment], request: SearchRequest) -> str:
    """Deliberately plain, deterministic prompt construction — no prompt-injection risk
    from listing data beyond what any LLM prompt already accepts as free text; nothing
    here executes anything the model returns.
    """
    lines = [
        f"Summarize this rental search in 2-3 sentences for a renter.",
        f"Location: {request.location}",
        f"Results: {len(ranked)} ranked listings.",
    ]
    for entry in ranked[:10]:
        lines.append(
            f"- #{entry.rank}: {entry.apartment.title}, ${entry.apartment.current_price:.0f}/mo, "
            f"score {entry.score:.2f}"
        )
    return "\n".join(lines)


register_provider(OllamaAIProvider())
