"""Reference/demo connector.

This is **not a real rental platform** — it fetches a local HTML fixture
(fixtures/demo_platform/listings.html) via a real Playwright browser and parses it with
BeautifulSoup, exactly like a connector for a real site would, but without touching any
live commercial website or its ToS. It exists to prove the full pipeline (Discovery ->
Connector -> Collector -> Analysis -> Ranking -> Report) works end-to-end while the actual
first platform target remains an open product decision (see notes/Questions.md).

v2.0 Step 5 — rebuilt on `src.connectors.sdk.BaseConnector`. What used to be one
`search()` method doing fetch+save+parse all at once (v1.0/v1.1) is now three small,
genuinely platform-specific hooks (`build_url`, `parse`, `normalize`) plus
`connector_info` — fetching, raw-page persistence, and validation are inherited, not
reimplemented. See docs/18_Connector_SDK.md.
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, Tag

from src.connectors.base import RawListing
from src.connectors.sdk import BaseConnector, ConnectorMetadata, register_connector
from src.search.search_request import SearchRequest

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "demo_platform"
_DEFAULT_FIXTURE_FILENAME = "listings.html"

# v2.6 Milestone 2.6.4 — a swappable module-level default, not a per-instance
# option: real callers (ConnectorFactory, the CLI, the dashboard) always
# instantiate this connector with no arguments and always get the one
# permanent "week 1" catalog. Only `tests.support.use_demo_fixture_snapshot()`
# reassigns this, temporarily, so a test can run monitoring twice against two
# genuinely different, deterministic snapshots — see
# fixtures/demo_platform/listings_week2.html and
# docs/41_Version_2.6_Planning.md Milestone 2.6.4. `build_url()` reads this at
# call time (not a frozen `_FIXTURE_PATH` constant) specifically so that swap
# takes effect on the connector's *next* search, exactly like a real second
# monitoring run observing the platform some time later would.
_active_fixture_filename = _DEFAULT_FIXTURE_FILENAME


@register_connector
class DemoPlatformConnector(BaseConnector):
    platform_id = "demo_platform"

    def build_url(self, request: SearchRequest) -> str:
        """Fetches the fixture's one fixed catalog regardless of `request` — a real
        connector would build its actual query URL from `request.location`/`.criteria`;
        this demo has nothing to query differently.
        """
        return (_FIXTURES_DIR / _active_fixture_filename).as_uri()

    def parse(self, raw_response: str) -> list[Tag]:
        soup = BeautifulSoup(raw_response, "lxml")
        return soup.select(".listing")

    def normalize(self, raw_record: Tag) -> RawListing:
        image_urls = [
            (_FIXTURES_DIR / img["src"]).resolve().as_uri() for img in raw_record.select(".photo")
        ]
        return RawListing(
            platform_listing_id=raw_record["data-listing-id"],
            title=raw_record.select_one(".title").get_text(strip=True),
            price=float(raw_record.select_one(".price").get_text(strip=True)),
            url=raw_record.select_one(".url")["href"],
            bedrooms=float(raw_record.select_one(".bedrooms").get_text(strip=True)),
            bathrooms=float(raw_record.select_one(".bathrooms").get_text(strip=True)),
            sqft=float(raw_record.select_one(".sqft").get_text(strip=True)),
            address_raw=raw_record.select_one(".address").get_text(strip=True),
            # v2.6 Milestone 2.6.4 — now read from the fixture (every listing in
            # both listings.html and listings_week2.html carries a real
            # `.status` span) instead of hardcoded, so the week2 snapshot can
            # express a genuine availability change. Week 1's value is always
            # "available", identical to the prior hardcoded behavior.
            status=raw_record.select_one(".status").get_text(strip=True),
            image_urls=image_urls,
            # v2.6 Milestone 2.6.2 — the fixture now carries these too, so the
            # currency/property_type filters and the geographic engine have real
            # evidence to work with instead of always-None. See
            # docs/41_Version_2.6_Planning.md.
            currency=raw_record.select_one(".currency").get_text(strip=True),
            property_type=raw_record.select_one(".property_type").get_text(strip=True),
            latitude=float(raw_record.select_one(".latitude").get_text(strip=True)),
            longitude=float(raw_record.select_one(".longitude").get_text(strip=True)),
        )

    def connector_info(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            connector_name="demo_platform",
            platform_name="Demo Platform (reference/demo connector, not real)",
            version="1.0.0",
            supported_countries=["N/A (local fixture)"],
            supported_cities=["N/A (local fixture)"],
            supported_rental_types=["apartment"],
            supports_images=True,
            supports_availability=True,
            supports_coordinates=True,
        )
