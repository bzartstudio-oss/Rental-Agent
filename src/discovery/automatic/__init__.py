"""The Automatic Platform Discovery Agent — a provider-independent system that
discovers, evaluates, classifies, and stores rental platform candidates. See
docs/29_Automatic_Platform_Discovery.md.

Importing this package imports `discovery.automatic.providers`, which is what
runs every built-in discovery provider's `register_discovery_provider(...)` call.
Public API re-exported here so callers don't need to know this package's internal
file layout — mirrors `src.feedback`/`src.ranking_v2`'s own re-export shape.
"""

from __future__ import annotations

from src.discovery.automatic import providers as _providers  # noqa: F401 — self-registration side effect
from src.discovery.automatic.agent import AutomaticDiscoveryAgent
from src.discovery.automatic.base_provider import DiscoveryProvider
from src.discovery.automatic.exceptions import (
    DiscoveryConfigurationError,
    DiscoveryException,
    DiscoveryProviderError,
    DiscoveryValidationError,
)
from src.discovery.automatic.factory import DiscoveryProviderFactory
from src.discovery.automatic.metadata import DiscoveryProviderMetadata
from src.discovery.automatic.models import (
    DiscoveredURL,
    DiscoveryComparison,
    DiscoveryPolicy,
    DiscoveryRequest,
    DiscoveryRun,
    DiscoveryStatistics,
    PlatformCandidate,
    PlatformCapabilityEstimate,
    PlatformClassification,
    PlatformDiscoveryResult,
    PlatformEvaluation,
    PlatformEvidence,
    PlatformStatus,
    PlatformVerificationResult,
)
from src.discovery.automatic.registry import DiscoveryProviderRegistry, register_discovery_provider

__all__ = [
    "AutomaticDiscoveryAgent",
    "DiscoveryProvider",
    "DiscoveryException",
    "DiscoveryConfigurationError",
    "DiscoveryProviderError",
    "DiscoveryValidationError",
    "DiscoveryProviderFactory",
    "DiscoveryProviderMetadata",
    "DiscoveredURL",
    "DiscoveryComparison",
    "DiscoveryPolicy",
    "DiscoveryRequest",
    "DiscoveryRun",
    "DiscoveryStatistics",
    "PlatformCandidate",
    "PlatformCapabilityEstimate",
    "PlatformClassification",
    "PlatformDiscoveryResult",
    "PlatformEvaluation",
    "PlatformEvidence",
    "PlatformStatus",
    "PlatformVerificationResult",
    "DiscoveryProviderRegistry",
    "register_discovery_provider",
]
