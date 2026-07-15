"""`BaseConnector` — every rental-platform connector's common ancestor. See
docs/18_Connector_SDK.md "Architecture" / "Lifecycle" for the full picture; this
docstring covers the template-method shape only.

`search()` is implemented once, here, and never overridden: it sequences
`connect() -> fetch_listing() -> parse() -> normalize() (per record) -> validate()`,
wraps the whole thing in timing + structured error handling, and returns one
`ConnectorResult` regardless of what happened. A new connector for a new platform
implements exactly `build_url()`, `parse()`, `normalize()`, and `connector_info()` —
four small, genuinely platform-specific methods — and inherits everything else
(fetching via Playwright by default, raw-page persistence, validation, health
reporting, capability discovery) for free. That's the whole point of this file: "adding
a new rental platform requires creating only one new connector folder with minimal
custom code."
"""

from __future__ import annotations

import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from src.collectors import raw_page_store
from src.collectors.browser_collector import BrowserCollector
from src.connectors.base import RawListing
from src.connectors.sdk.configuration import ConnectorConfiguration
from src.connectors.sdk.exceptions import ConnectorConnectionError, ConnectorException, ConnectorValidationError
from src.connectors.sdk.metadata import ConnectorCapabilities, ConnectorMetadata
from src.connectors.sdk.result import ConnectorResult
from src.connectors.sdk.validator import ConnectorValidator, ValidationResult
from src.knowledge import knowledge_service
from src.search.search_request import SearchRequest


class BaseConnector(ABC):
    """`platform_id` is a required class attribute (e.g. `platform_id = "demo_platform"`)
    — it's both this connector's identity (matches its row in `platforms`) and its
    `ConnectorRegistry` key, read at `@register_connector` decoration time.
    """

    platform_id: str

    def __init__(self, config: ConnectorConfiguration | None = None) -> None:
        self.config = config or ConnectorConfiguration()

    # ------------------------------------------------------------------
    # Lifecycle — connect()/disconnect() default to no-ops. Override for a
    # connector that needs e.g. an authenticated session established once per
    # search rather than reconstructed per page (a login-required platform).
    # ------------------------------------------------------------------

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    # ------------------------------------------------------------------
    # The template method. Never override this — override the hooks below.
    # ------------------------------------------------------------------

    def search(self, request: SearchRequest) -> ConnectorResult:
        """`connect()` is called *inside* the `try` block below (v2.0 Step 7 fix — was
        outside it in the original Step 5 implementation, undetected because both
        reference connectors' `connect()` is a no-op). `RentCastConnector.connect()`
        is the first one that actually raises (`ConnectorConfigurationError` when no
        API key is configured); with `connect()` outside the guard, that exception
        would have propagated straight out of `search()`, breaking the "search()
        never raises" guarantee documented above.
        """
        started_at = datetime.now(timezone.utc)
        start_perf = time.perf_counter()

        try:
            self.connect()
            raw_response = self.fetch_listing(request)
            raw_records = self.parse(raw_response)
            listings = [self.normalize(record) for record in raw_records]
            validation_results = self.validate(listings)
            warnings = [warning for result in validation_results for warning in result.warnings]

            if self.config.strict_validation and any(not result.is_valid for result in validation_results):
                raise ConnectorValidationError(
                    f"{self.platform_id}: one or more listings failed validation "
                    f"({sum(1 for r in validation_results if not r.is_valid)} of {len(validation_results)})"
                )

            return ConnectorResult(
                platform_id=self.platform_id,
                listings=listings,
                success=True,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                response_time_ms=int((time.perf_counter() - start_perf) * 1000),
                validation_warnings=warnings,
            )
        except ConnectorException as exc:
            return self._failed_result(started_at, start_perf, str(exc))
        except Exception as exc:
            return self._failed_result(started_at, start_perf, str(ConnectorConnectionError(f"{self.platform_id}: {exc}")))
        finally:
            self.disconnect()

    def _failed_result(self, started_at: datetime, start_perf: float, error: str) -> ConnectorResult:
        return ConnectorResult(
            platform_id=self.platform_id,
            listings=[],
            success=False,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            response_time_ms=int((time.perf_counter() - start_perf) * 1000),
            error=error,
        )

    # ------------------------------------------------------------------
    # Hooks with a useful default — override individual pieces, not the whole
    # sequence, to change transport (e.g. an HTTP API instead of a browser).
    # ------------------------------------------------------------------

    def fetch_listing(self, request: SearchRequest) -> Any:
        """Default: build the URL, fetch it via `_collect(url)` (Playwright by
        default), and persist the raw response through `raw_page_store` — every
        connector gets this for free. Override this whole method only if a platform's
        "fetch" isn't a single URL (e.g. paginated requests joined into one response);
        override just `_collect()` to change *how* a URL is fetched (e.g. HTTP instead
        of a browser) while keeping this sequencing.
        """
        url = self.build_url(request)
        raw_response = self._collect(url)
        raw_page_store.save_page(self.platform_id, raw_response if isinstance(raw_response, str) else str(raw_response))
        return raw_response

    def _collect(self, url: str) -> str:
        """Default transport: `BrowserCollector` (Playwright). Override this one
        method — not `fetch_listing()` — for a platform with a usable HTTP API:
        `from src.collectors import http_collector; return http_collector.fetch_text(url)`.
        Keeps `build_url()`/`parse()`/`normalize()` identical regardless of transport.
        """
        with BrowserCollector(headless=self.config.headless, timeout_ms=self.config.timeout_ms) as browser:
            return browser.fetch(url)

    def validate(self, listings: list[RawListing]) -> list[ValidationResult]:
        return ConnectorValidator.validate_all(listings)

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(self.connector_info())

    def supports(self, capability: str) -> bool:
        return self.capabilities().supports(capability)

    def health_check(self, conn: sqlite3.Connection):
        """The Knowledge Engine (v2.0 Step 4) already tracks exactly this — successes,
        failures, average runtime, last success/failure — per platform, in
        `platform_performance_observations`. Reused here, not reimplemented: see
        `src.knowledge.knowledge_service.connector_health()` and
        `docs/18_Connector_SDK.md` "Connector Health" for why there's only one
        `ConnectorHealth` class in this codebase, not two.
        """
        results = knowledge_service.connector_health(conn, platform_id=self.platform_id)
        return results[0] if results else None

    # ------------------------------------------------------------------
    # Genuinely platform-specific — every connector must implement these.
    # ------------------------------------------------------------------

    @abstractmethod
    def build_url(self, request: SearchRequest) -> str:
        """Turn a `SearchRequest` (location + criteria) into this platform's query
        URL. The one place a connector reads `request.location`/`request.criteria`.
        """
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw_response: Any) -> list[Any]:
        """Turn the raw fetched response into a list of platform-native listing
        records (BeautifulSoup elements, JSON dict entries, XML nodes, CSV rows —
        whatever this platform's format naturally produces). Each record is handed to
        `normalize()` next; this method does not build `RawListing`s itself.
        """
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_record: Any) -> RawListing:
        """Turn ONE platform-native record (from `parse()`) into one `RawListing` —
        the shared shape every connector, regardless of source format, must produce.
        """
        raise NotImplementedError

    @abstractmethod
    def connector_info(self) -> ConnectorMetadata:
        """This connector's static self-description — name, version, coverage, which
        optional data it can supply. One instance per connector class, not per search.
        """
        raise NotImplementedError
