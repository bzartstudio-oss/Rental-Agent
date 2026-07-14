"""Reference/demo connector.

This is **not a real rental platform** — it fetches a local HTML fixture
(fixtures/demo_platform/listings.html) via a real Playwright browser and parses it with
BeautifulSoup, exactly like a connector for a real site would, but without touching any
live commercial website or its ToS. It exists to prove the full pipeline (Discovery ->
Connector -> Collector -> Analysis -> Ranking -> Report) works end-to-end while the actual
first platform target remains an open product decision (see notes/Questions.md).

Swapping in a real platform later means writing one more connector implementing the same
Connector contract (see base.py) — nothing else in the pipeline needs to change. That's
the whole point of the boundary described in docs/06_Connector_Framework.md.
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from src.collectors import raw_page_store
from src.collectors.browser_collector import BrowserCollector
from src.connectors.base import Connector, RawListing

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_platform" / "listings.html"


class DemoPlatformConnector(Connector):
    platform_id = "demo_platform"

    def search(self, criteria: dict) -> list[RawListing]:
        """Fetches and returns every listing in the fixture, ignoring `criteria` — a real
        connector would use `criteria` to build its actual query URL/params; this demo
        has exactly one fixed catalog, so there's nothing to query differently.
        """
        with BrowserCollector() as browser:
            html = browser.fetch(_FIXTURE_PATH.as_uri())

        raw_page_store.save_page(self.platform_id, html)

        return self._parse(html)

    def _parse(self, html: str) -> list[RawListing]:
        soup = BeautifulSoup(html, "lxml")
        listings = []

        for element in soup.select(".listing"):
            image_urls = [
                (_FIXTURE_PATH.parent / img["src"]).resolve().as_uri()
                for img in element.select(".photo")
            ]
            listings.append(
                RawListing(
                    platform_listing_id=element["data-listing-id"],
                    title=element.select_one(".title").get_text(strip=True),
                    price=float(element.select_one(".price").get_text(strip=True)),
                    url=element.select_one(".url")["href"],
                    bedrooms=float(element.select_one(".bedrooms").get_text(strip=True)),
                    bathrooms=float(element.select_one(".bathrooms").get_text(strip=True)),
                    sqft=float(element.select_one(".sqft").get_text(strip=True)),
                    address_raw=element.select_one(".address").get_text(strip=True),
                    status="available",
                    image_urls=image_urls,
                )
            )

        return listings


# Convention core/agent.py relies on to dynamically load a connector from the
# `connector_module` string stored in the platforms table — see
# docs/06_Connector_Framework.md "Adding a New Connector": every connector module must
# expose a module-level CONNECTOR constant pointing at its Connector subclass.
CONNECTOR = DemoPlatformConnector
