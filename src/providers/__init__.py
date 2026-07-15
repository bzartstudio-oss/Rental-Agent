"""The Provider abstraction layer — a common interface + registry + scoring router for
both data providers (RentCast, local demo) and AI providers (Ollama, a no-op fallback).
See docs/21_Provider_Abstraction_Layer.md.

Importing this package imports `providers.data`/`providers.ai`, which is what runs
every built-in provider's `register_provider(...)` call — the same eager,
"small known set" self-registration `src.analysis.analyzers` already established.
"""

from __future__ import annotations

from src.providers import data as _data  # noqa: F401 — import for self-registration side effect
from src.providers import ai as _ai  # noqa: F401 — import for self-registration side effect
from src.providers.base import Provider, ProviderKind
from src.providers.exceptions import NoProviderAvailableError, ProviderConfigurationError, ProviderException
from src.providers.registry import ProviderRegistry, register_provider
from src.providers.router import ProviderAttempt, ProviderRouter, ProviderRunOutcome
from src.providers.scoring import DEFAULT_WEIGHTS, ProviderMetadata, ProviderScore, ScoringWeights, score_provider

__all__ = [
    "Provider",
    "ProviderKind",
    "ProviderException",
    "ProviderConfigurationError",
    "NoProviderAvailableError",
    "ProviderRegistry",
    "register_provider",
    "ProviderRouter",
    "ProviderRunOutcome",
    "ProviderAttempt",
    "ProviderMetadata",
    "ProviderScore",
    "ScoringWeights",
    "DEFAULT_WEIGHTS",
    "score_provider",
]
