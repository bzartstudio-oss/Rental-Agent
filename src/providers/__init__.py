"""The Production Provider Framework — a common interface + registry + factory +
scoring router + health/metrics/statistics + validation, for both data providers
(RentCast, local demo) and AI providers (Ollama, a no-op fallback). See
docs/21_Provider_Abstraction_Layer.md (registry/router/scoring, v2.5 Step 8's
foundation) and docs/24_Production_Providers.md (factory/configuration/health/
metrics/statistics/validator, added in v2.5 Step 8 itself).

Importing this package imports `providers.data`/`providers.ai`, which is what runs
every built-in provider's `register_provider(...)` call — the same eager,
"small known set" self-registration `src.analysis.analyzers` already established.

Public API, re-exported here so callers don't need to know this package's internal
file layout — mirrors `src.connectors.sdk`'s own re-export shape.
"""

from __future__ import annotations

from src.providers import data as _data  # noqa: F401 — import for self-registration side effect
from src.providers import ai as _ai  # noqa: F401 — import for self-registration side effect
from src.providers.base import Provider, ProviderKind
from src.providers.configuration import ProviderConfiguration
from src.providers.exceptions import (
    NoProviderAvailableError,
    ProviderConfigurationError,
    ProviderException,
    ProviderValidationError,
)
from src.providers.factory import ProviderFactory
from src.providers.health import ProviderHealth, check_provider_health
from src.providers.metrics import ProviderMetrics, build_provider_metrics, record_provider_metrics
from src.providers.registry import ProviderRegistry, register_provider
from src.providers.router import ProviderAttempt, ProviderRouter, ProviderRunOutcome
from src.providers.scoring import DEFAULT_WEIGHTS, ProviderMetadata, ProviderScore, ScoringWeights, score_provider
from src.providers.statistics import ProviderStatistics, provider_statistics
from src.providers.validator import ProviderValidationResult, ProviderValidator

__all__ = [
    "Provider",
    "ProviderKind",
    "ProviderException",
    "ProviderConfigurationError",
    "ProviderValidationError",
    "NoProviderAvailableError",
    "ProviderRegistry",
    "register_provider",
    "ProviderFactory",
    "ProviderConfiguration",
    "ProviderRouter",
    "ProviderRunOutcome",
    "ProviderAttempt",
    "ProviderMetadata",
    "ProviderScore",
    "ScoringWeights",
    "DEFAULT_WEIGHTS",
    "score_provider",
    "ProviderHealth",
    "check_provider_health",
    "ProviderMetrics",
    "build_provider_metrics",
    "record_provider_metrics",
    "ProviderStatistics",
    "provider_statistics",
    "ProviderValidationResult",
    "ProviderValidator",
]
