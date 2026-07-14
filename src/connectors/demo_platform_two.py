"""A second reference/demo connector — see docs/10_Roadmap.md Phase 7.

Deliberately parses a differently-shaped fixture (table/tr/td markup, different class
names, `data-id` instead of `data-listing-id`) than connectors/demo_platform.py, to prove
the Connector abstraction genuinely isolates platform-specific parsing: adding this file
required zero changes to analyzers/, ranking/, storage/, or services/ — see
docs/01_System_Architecture.md "The Independence Guardrail".

Not a real rental platform, same as demo_platform.py — see that module's docstring.
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from src.collectors import raw_page_store
from src.collectors.browser_collector import BrowserCollector
from src.connectors.base import Connector, RawListing

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_platform_two" / "listings.html"


class DemoPlatformTwoConnector(Connector):
    platform_id = "demo_platform_two"

    def search(self, criteria: dict) -> list[RawListing]:
        with BrowserCollector() as browser:
            html = browser.fetch(_FIXTURE_PATH.as_uri())

        raw_page_store.save_page(self.platform_id, html)

        return self._parse(html)

    def _parse(self, html: str) -> list[RawListing]:
        soup = BeautifulSoup(html, "lxml")
        listings = []

        for row in soup.select(".row"):
            image_urls = [
                (_FIXTURE_PATH.parent / img["src"]).resolve().as_uri() for img in row.select(".pic")
            ]
            listings.append(
                RawListing(
                    platform_listing_id=row["data-id"],
                    title=row.select_one(".name").get_text(strip=True),
                    price=float(row.select_one(".rent").get_text(strip=True)),
                    url=row.select_one(".link")["href"],
                    bedrooms=float(row.select_one(".beds").get_text(strip=True)),
                    bathrooms=float(row.select_one(".baths").get_text(strip=True)),
                    sqft=float(row.select_one(".area").get_text(strip=True)),
                    address_raw=row.select_one(".loc").get_text(strip=True),
                    status="available",
                    image_urls=image_urls,
                )
            )

        return listings


CONNECTOR = DemoPlatformTwoConnector
