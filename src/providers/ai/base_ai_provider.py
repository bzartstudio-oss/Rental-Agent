"""`AIProvider` — a `Provider` whose job is summarizing/enriching an already-ranked
search with natural-language text. Entirely optional and additive: nothing downstream
of `core/agent.py` requires an AI summary to exist (see
`services/report_generator.py`'s `ai_summary` parameter — `None` renders nothing).
"""

from __future__ import annotations

from abc import abstractmethod

from src.providers.base import Provider, ProviderKind
from src.providers.configuration import ProviderConfiguration
from src.ranking.ranking_engine import RankedApartment
from src.search.search_request import SearchRequest


class AIProvider(Provider):
    kind = ProviderKind.AI

    @abstractmethod
    def summarize(
        self,
        ranked: list[RankedApartment],
        request: SearchRequest,
        config: ProviderConfiguration | None = None,
    ) -> str | None:
        """Returns a short natural-language summary of the ranked results, or `None`
        if this provider genuinely has nothing to say (never a fabricated placeholder
        string — the same "None means no evidence" convention the Deep Analysis Engine
        established in v2.0 Step 6). Raising is reserved for a real operational
        failure (the local Ollama server unreachable mid-call, a malformed response) —
        `ProviderRouter.run_with_fallback()` treats that as "try the next AI provider,"
        exactly like a failed data-provider call.

        `config` defaults to `None` (every pre-v2.5-Step-8 call site keeps working
        unchanged) — when given, `config.timeout_ms` overrides a concrete provider's
        own default request timeout.
        """
        raise NotImplementedError
