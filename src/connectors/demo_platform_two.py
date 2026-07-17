"""A second reference/demo connector — see docs/10_Roadmap.md Phase 7.

Deliberately parses a differently-shaped fixture (table/tr/td markup, different class
names, `data-id` instead of `data-listing-id`) than connectors/demo_platform.py, to prove
the Connector abstraction genuinely isolates platform-specific parsing: adding this file
required zero changes to analyzers/, ranking/, storage/, or services/ — see
docs/01_System_Architecture.md "The Independence Guardrail".

Not a real rental platform, same as demo_platform.py — see that module's docstring.

v2.0 Step 5 — rebuilt on `src.connectors.sdk.BaseConnector`, same as demo_platform.py.
Proves the SDK itself isolates platform-specific parsing the same way the original
Connector contract did: only `build_url`/`parse`/`normalize`/`connector_info` differ
between this file and demo_platform.py.
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, Tag

from src.connectors.base import RawListing
from src.connectors.sdk import BaseConnector, ConnectorMetadata, register_connector
from src.search.search_request import SearchRequest

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_platform_two" / "listings.html"


@register_connector
class DemoPlatformTwoConnector(BaseConnector):
    platform_id = "demo_platform_two"

    def build_url(self, request: SearchRequest) -> str:
        return _FIXTURE_PATH.as_uri()

    def parse(self, raw_response: str) -> list[Tag]:
        soup = BeautifulSoup(raw_response, "lxml")
        return soup.select(".row")

    def normalize(self, raw_record: Tag) -> RawListing:
        image_urls = [
            (_FIXTURE_PATH.parent / img["src"]).resolve().as_uri() for img in raw_record.select(".pic")
        ]
        return RawListing(
            platform_listing_id=raw_record["data-id"],
            title=raw_record.select_one(".name").get_text(strip=True),
            price=float(raw_record.select_one(".rent").get_text(strip=True)),
            url=raw_record.select_one(".link")["href"],
            bedrooms=float(raw_record.select_one(".beds").get_text(strip=True)),
            bathrooms=float(raw_record.select_one(".baths").get_text(strip=True)),
            sqft=float(raw_record.select_one(".area").get_text(strip=True)),
            address_raw=raw_record.select_one(".loc").get_text(strip=True),
            status="available",
            image_urls=image_urls,
            # v2.6 Milestone 2.6.2 — same rationale as demo_platform.py, parsed
            # from this fixture's own differently-named columns.
            currency=raw_record.select_one(".currency").get_text(strip=True),
            property_type=raw_record.select_one(".proptype").get_text(strip=True),
            latitude=float(raw_record.select_one(".lat").get_text(strip=True)),
            longitude=float(raw_record.select_one(".lng").get_text(strip=True)),
        )

    def connector_info(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            connector_name="demo_platform_two",
            platform_name="Demo Platform Two (reference/demo connector, not real)",
            version="1.0.0",
            supported_countries=["N/A (local fixture)"],
            supported_cities=["N/A (local fixture)"],
            supported_rental_types=["apartment"],
            supports_images=True,
            supports_availability=True,
            supports_coordinates=True,
        )
