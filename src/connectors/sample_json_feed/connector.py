"""SampleJsonFeedConnector — a third reference connector, built for the SDK
Validation Sprint (see docs/22_SDK_Validation_Sprint.md), not a real rental platform
(same convention as `demo_platform.py`/`demo_platform_two.py`: real code, a real local
fixture, no live commercial site touched).

Deliberately shaped nothing like either existing reference connector: a JSON feed
(field names like `headline`/`monthly_rent`/`full_address`, nested `coords`), not
HTML/BeautifulSoup — proof that `BaseConnector`'s `build_url`/`parse`/`normalize`
contract genuinely doesn't assume any particular source format, exactly as
`docs/18_Connector_SDK.md` claims ("a future JSON API... connector's `parse()` just
returns a different container type"). Overrides only `_collect()` (not
`fetch_listing()`) to change transport from Playwright to a plain local-file read —
proving that override point works too, distinct from RentCastConnector's approach
(which overrides `fetch_listing()` entirely for pagination).

This connector is intentionally **not** registered in `discovery/known_platforms.py`
— it exists purely to validate the SDK, not to be a real, seedable data source. See
docs/22_SDK_Validation_Sprint.md "Question 1" for why that's the stronger proof: every
test here resolves it via a directly-constructed `Platform`, exactly the way
`ConnectorFactory.get()` would for a real platform, with zero edits to any
pre-existing file.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from src.connectors.base import RawListing
from src.connectors.sdk import BaseConnector, ConnectorMetadata, register_connector
from src.search.search_request import SearchRequest

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "feed.json"


@register_connector
class SampleJsonFeedConnector(BaseConnector):
    platform_id = "sample_json_feed"

    def build_url(self, request: SearchRequest) -> str:
        return _FIXTURE_PATH.as_uri()

    def _collect(self, url: str) -> str:
        """Overrides just this one hook (not `fetch_listing()`) to swap transport
        from the default Playwright browser to a plain local-file read — a real,
        working second way to satisfy "override just `_collect()` to change *how* a
        URL is fetched" (`BaseConnector._collect.__doc__`), distinct from
        `RentCastConnector`'s approach of overriding `fetch_listing()` entirely.
        """
        return Path(url2pathname(urlparse(url).path)).read_text(encoding="utf-8")

    def parse(self, raw_response: str) -> list[dict]:
        return json.loads(raw_response)["listings"]

    def normalize(self, raw_record: dict) -> RawListing:
        """`raw_record["room_category"]` (`"private_room"`/`"entire_unit"`) is real
        data this feed provides — deliberately left unmapped below. There is no
        `RawListing.room_type` field to put it in; see
        docs/22_SDK_Validation_Sprint.md "Question 4, Finding 1" for why that's a
        genuine, undecided model gap rather than an oversight in this connector.
        Likewise `last_modified` (a real platform-native timestamp) has nowhere to
        go — see that doc's Finding 2.
        """
        coords = raw_record.get("coords") or {}
        image_urls = [
            (_FIXTURE_PATH.parent / photo).resolve().as_uri() for photo in raw_record.get("photo_urls", [])
        ]

        return RawListing(
            platform_listing_id=raw_record["listing_id"],
            title=raw_record["headline"],
            price=float(raw_record["monthly_rent"]),
            url=raw_record["detail_url"],
            bedrooms=raw_record.get("bed_count"),
            bathrooms=raw_record.get("bath_count"),
            sqft=raw_record.get("area_sqft"),
            address_raw=raw_record.get("full_address"),
            status="available" if raw_record.get("state") == "open" else raw_record.get("state"),
            image_urls=image_urls,
            description=raw_record.get("summary"),
            latitude=coords.get("lat"),
            longitude=coords.get("lng"),
            currency=raw_record.get("currency_code"),
            property_type=raw_record.get("unit_category"),
        )

    def connector_info(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            connector_name="sample_json_feed",
            platform_name="Sample JSON Feed (SDK validation connector, not a real rental site)",
            version="1.0.0",
            supported_countries=["N/A (local fixture)"],
            supported_cities=["N/A (local fixture)"],
            supported_rental_types=["apartment", "studio"],
            supports_images=True,
            supports_availability=True,
            supports_coordinates=True,
        )
