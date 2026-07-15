"""`DataProvider` — a `Provider` whose job is producing rental listings. Deliberately a
thin wrapper contract, not a reimplementation of `src.connectors.sdk.BaseConnector`:
every built-in `DataProvider` delegates its actual fetching to a real connector via
`ConnectorFactory`, so there is exactly one place (the Connector SDK) that knows how to
fetch/parse/normalize/validate — this layer only adds *which platform to use, and in
what order of preference*.
"""

from __future__ import annotations

from abc import abstractmethod

from src.connectors.sdk.result import ConnectorResult
from src.providers.base import Provider, ProviderKind
from src.providers.configuration import ProviderConfiguration
from src.search.search_request import SearchRequest


class DataProvider(Provider):
    """`platform_id` is the real `platforms.id` this provider's results should be
    attributed to when written through `analyzers/engine.py::process_listings()` —
    kept distinct from `provider_id` because they aren't always the same string (e.g.
    `LocalDemoDataProvider.provider_id == "local_demo"` but its underlying platform is
    `"demo_platform"`, the same row every other demo-connector test already uses).
    """

    kind = ProviderKind.DATA
    platform_id: str

    @abstractmethod
    def search(self, request: SearchRequest, config: ProviderConfiguration | None = None) -> ConnectorResult:
        """Returns the same `ConnectorResult` shape `BaseConnector.search()` returns —
        a `DataProvider` is a selection layer over connectors, not a competing result
        type. `ProviderRouter.run_with_fallback()`'s `is_success` check for data
        providers is simply `lambda result: result.success`.

        `config` defaults to `None` (every call site written before v2.5 Step 8,
        including `ProviderRouter.run_with_fallback()` lambdas, keeps working
        unchanged) — when given, a concrete `DataProvider` translates it into a
        `ConnectorConfiguration` at the point it calls `ConnectorFactory.get()`,
        rather than reimplementing timeout/retry/credential handling itself.
        """
        raise NotImplementedError
