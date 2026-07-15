"""RentCastConnector — the first production (non-demo) Connector SDK connector, added
in v2.0 Step 7. See docs/20_First_Production_Connector.md for the full write-up: why
RentCast was chosen over the six previously-catalogued platforms (none of which offer
a self-service API and all of which prohibit scraping in their published ToS), the
verified request/response schema, supported fields, and known limitations.

RentCast (https://www.rentcast.io) is a real, developer-facing REST API for US rental
data — `GET /listings/rental/long-term` at api.rentcast.io/v1, authenticated with an
`X-Api-Key` header, self-service signup, a free tier, and published Terms of Use that
permit this kind of programmatic access. No authentication is bypassed and no anti-bot/
CAPTCHA protection is circumvented — this is the platform's own supported integration
path, not a workaround.
"""

from __future__ import annotations

import json
import os
from typing import Any

from src.collectors import raw_page_store
from src.connectors.base import RawListing
from src.connectors.rentcast.client import RentCastClient, RentCastClientError
from src.connectors.sdk import BaseConnector, ConnectorMetadata, register_connector
from src.connectors.sdk.configuration import ConnectorConfiguration
from src.connectors.sdk.exceptions import (
    ConnectorConfigurationError,
    ConnectorConnectionError,
    ConnectorParsingError,
)
from src.search.search_request import SearchRequest
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Conservative pagination defaults. RentCast's free tier is 50 requests/month — a
# single search must never have the ability to silently exhaust it. 100/page, at most
# 3 pages, bounds one platform search to at most 3 API calls regardless of how many
# listings actually exist for the queried area.
_PAGE_SIZE = 100
_MAX_PAGES = 3


@register_connector
class RentCastConnector(BaseConnector):
    platform_id = "rentcast"

    def __init__(self, config: ConnectorConfiguration | None = None) -> None:
        super().__init__(config)
        self._api_key: str | None = None

    def connect(self) -> None:
        """Reads the API key from `ConnectorConfiguration.credentials["api_key"]` first
        (the SDK-sanctioned per-instance override), falling back to the
        `RENTCAST_API_KEY` environment variable. The fallback matters because
        `core/agent.py` constructs every connector through
        `ConnectorFactory.get(platform)` with no per-platform config
        (docs/01_System_Architecture.md "No connector-specific code in the Research
        Agent") — an environment variable is the only channel this connector can read
        its own credential from without that changing. Raises
        `ConnectorConfigurationError` if neither is set; `BaseConnector.search()` always
        calls `connect()` inside its own try/except, so this never propagates to the
        caller as a bare exception — it becomes a normal, inspectable failed
        `ConnectorResult`.
        """
        api_key = None
        if self.config.credentials:
            api_key = self.config.credentials.get("api_key")
        api_key = api_key or os.environ.get("RENTCAST_API_KEY")

        if not api_key:
            raise ConnectorConfigurationError(
                "rentcast: no API key configured — set "
                "ConnectorConfiguration(credentials={'api_key': ...}) or the "
                "RENTCAST_API_KEY environment variable"
            )
        self._api_key = api_key

    def build_url(self, request: SearchRequest) -> str:
        """RentCast is a query-parameter API, not a series of per-page URLs — this
        returns the (fixed) endpoint alone, for logging/traceability. The actual query
        parameters are built by `_build_params()` and used directly by
        `fetch_listing()`, which this connector overrides entirely (see its docstring).
        """
        return f"{RentCastClient.BASE_URL}{RentCastClient.RENTAL_LISTINGS_ENDPOINT}"

    def fetch_listing(self, request: SearchRequest) -> Any:
        """Overrides `BaseConnector`'s default entirely — RentCast's "fetch" is a
        paginated series of HTTP calls, not a single URL to hand to `_collect()`. Every
        page's records are combined and saved as one JSON raw capture via
        `raw_page_store`, the same audit trail every other connector gets, just with
        `suffix="json"` instead of the default `"html"`.
        """
        client = RentCastClient(
            api_key=self._api_key,
            timeout_ms=self.config.timeout_ms,
            max_retries=self.config.max_retries,
        )
        params = self._build_params(request)

        records: list[dict] = []
        offset = 0
        for _ in range(_MAX_PAGES):
            page_params = {**params, "limit": _PAGE_SIZE, "offset": offset}
            try:
                page = client.get_rental_listings(page_params)
            except RentCastClientError as exc:
                raise ConnectorConnectionError(f"rentcast: {exc}") from exc

            if not isinstance(page, list):
                raise ConnectorParsingError(
                    f"rentcast: expected a list of listings, got {type(page).__name__}"
                )

            records.extend(page)
            logger.info("rentcast page fetched", extra={"offset": offset, "count": len(page)})

            if len(page) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE

        raw_page_store.save_page(self.platform_id, json.dumps(records), suffix="json")
        return records

    def _build_params(self, request: SearchRequest) -> dict[str, Any]:
        """`SearchRequest.location` is a free-text string — its structured shape is
        still an open question (docs/04_Search_Request.md) — so this splits on the
        first comma into city/state; a location with no comma is sent as `city` alone.
        A known, honest limitation: RentCast's `city`/`state` params are exact-match,
        so an unusually formatted location can return zero results rather than a
        fuzzy match.

        Bedroom/bathroom/sqft/price criteria are deliberately NOT translated into
        RentCast query params: RentCast's `bedrooms`/`bathrooms`/`squareFootage`
        params are exact-match, not minimum thresholds, so sending e.g. `min_bedrooms`
        as `bedrooms` would incorrectly exclude larger, still-matching apartments.
        That filtering already happens downstream, generically, for every connector
        regardless of platform (`src/search/criteria.py`'s hard-filter pass) — doing it
        again here would be redundant at best and wrong at worst.
        """
        parts = [part.strip() for part in request.location.split(",", 1)]
        params: dict[str, Any] = {}
        if parts[0]:
            params["city"] = parts[0]
        if len(parts) == 2 and parts[1]:
            params["state"] = parts[1]
        params["status"] = "Active"
        return params

    def parse(self, raw_response: list[dict]) -> list[dict]:
        """`fetch_listing()` already returns a combined list of listing dicts (the
        pagination/combining happens there, not here) — this is passthrough, kept as
        its own method only so this connector's shape matches every other connector's
        (`build_url`/`parse`/`normalize`/`connector_info`), per docs/18_Connector_SDK.md.
        """
        return raw_response

    def normalize(self, raw_record: dict) -> RawListing:
        """Maps one RentCast listing dict into a `RawListing` — see
        docs/20_First_Production_Connector.md "Supported Fields" for the complete
        mapping table. RentCast's schema has neither a photos/images field nor a
        description field; both are set to their honest "not provided" values (`[]` /
        `None`) rather than fabricated. RentCast also has no single browsable listing
        page — `url` (a required, non-optional `RawListing` field) is set to this
        listing's own RentCast API record (`GET /listings/rental/long-term/{id}`), the
        most accurate non-fabricated reference the platform can offer, not a page a
        person could open in a browser.
        """
        listing_id = raw_record.get("id")
        if not listing_id:
            raise ConnectorParsingError("rentcast: listing record is missing its 'id' field")

        status = raw_record.get("status")
        return RawListing(
            platform_listing_id=str(listing_id),
            title=raw_record.get("formattedAddress") or str(listing_id),
            price=float(raw_record.get("price") or 0.0),
            url=f"{RentCastClient.BASE_URL}{RentCastClient.RENTAL_LISTINGS_ENDPOINT}/{listing_id}",
            bedrooms=raw_record.get("bedrooms"),
            bathrooms=raw_record.get("bathrooms"),
            sqft=raw_record.get("squareFootage"),
            address_raw=raw_record.get("formattedAddress"),
            status="available" if status == "Active" else status,
            image_urls=[],
            description=None,
            latitude=raw_record.get("latitude"),
            longitude=raw_record.get("longitude"),
            # RentCast covers US listings only — every price it returns is USD.
            currency="USD",
            property_type=raw_record.get("propertyType"),
        )

    def connector_info(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            connector_name="rentcast",
            platform_name="RentCast",
            version="1.0.0",
            supported_countries=["United States"],
            supported_cities=["Nationwide (United States)"],
            supported_rental_types=["apartment", "house", "condo", "townhouse"],
            supported_languages=["en"],
            supports_images=False,
            supports_availability=True,
            supports_coordinates=True,
            supports_pagination=True,
            # RentCast's real limit is monthly (50 requests/month on the free tier),
            # not per-minute — None means "no *per-minute* limit is known", the same
            # nullable-means-no-evidence convention ConnectorMetadata already uses
            # elsewhere, not "unlimited".
            rate_limit_per_minute=None,
        )
