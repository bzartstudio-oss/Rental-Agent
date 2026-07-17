"""v2.0 Step 5: DemoPlatformConnector rebuilt on BaseConnector — same fixture, same
expected listings, but now through `connector.search(SearchRequest)` returning a
`ConnectorResult` instead of `connector.search(criteria=dict)` returning a bare list.
"""

import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from src.connectors.demo_platform import DemoPlatformConnector
from src.search.search_request import SearchRequest
from tests.connectors.sdk.certification import ConnectorCertificationMixin
from tests.support import isolated_collectors, use_demo_fixture_snapshot


def _file_uri_to_path(uri: str) -> Path:
    return Path(url2pathname(urlparse(uri).path))


class DemoPlatformConnectorCertificationTests(ConnectorCertificationMixin, unittest.TestCase):
    connector_class = DemoPlatformConnector
    search_request = SearchRequest(location="Example City")

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()


class DemoPlatformConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def _search(self):
        connector = DemoPlatformConnector()
        return connector.search(SearchRequest(location="Example City"))

    def test_search_returns_a_successful_result_with_all_three_fixture_listings(self) -> None:
        result = self._search()

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.results_count, 3)
        self.assertEqual(
            {listing.platform_listing_id for listing in result.listings},
            {"demo-001", "demo-002", "demo-003"},
        )

    def test_listing_fields_are_parsed_correctly(self) -> None:
        result = self._search()
        listings = {listing.platform_listing_id: listing for listing in result.listings}
        studio = listings["demo-002"]

        self.assertEqual(studio.title, "Cozy Studio, Walk to Downtown")
        self.assertEqual(studio.price, 950.0)
        self.assertEqual(studio.bedrooms, 0.0)
        self.assertEqual(studio.bathrooms, 1.0)
        self.assertEqual(studio.sqft, 420.0)
        self.assertEqual(studio.address_raw, "45 Sample Avenue, Example City")
        self.assertTrue(studio.url.startswith("https://"))

    def test_currency_property_type_and_coordinates_are_parsed(self) -> None:
        """v2.6 Milestone 2.6.2 — see docs/41_Version_2.6_Planning.md. Before this,
        the fixture never carried these fields at all, so every demo apartment's
        `currency`/`property_type`/`latitude`/`longitude` was always `None`.
        """
        result = self._search()
        listings = {listing.platform_listing_id: listing for listing in result.listings}

        for listing in listings.values():
            self.assertEqual(listing.currency, "EUR")
            self.assertIsInstance(listing.property_type, str)
            self.assertTrue(listing.property_type)
            self.assertIsInstance(listing.latitude, float)
            self.assertIsInstance(listing.longitude, float)

        self.assertEqual(listings["demo-002"].property_type, "studio")
        self.assertEqual(listings["demo-001"].property_type, "apartment")
        self.assertEqual(listings["demo-001"].latitude, 39.4790)
        self.assertEqual(listings["demo-001"].longitude, -0.3500)

    def test_image_urls_resolve_to_real_existing_files(self) -> None:
        result = self._search()

        for listing in result.listings:
            self.assertEqual(len(listing.image_urls), 1)
            image_path = _file_uri_to_path(listing.image_urls[0])
            self.assertTrue(image_path.exists(), f"{image_path} should exist")
            self.assertTrue(image_path.read_bytes().startswith(b"\x89PNG"))

    def test_search_saves_a_raw_page_capture(self) -> None:
        self._search()

        captured_files = list(Path(self._tmp_dir.name).glob("raw_pages/demo_platform/*.html"))
        self.assertEqual(len(captured_files), 1)
        self.assertIn("Demo Rentals", captured_files[0].read_text(encoding="utf-8"))

    def test_no_validation_warnings_for_a_fully_populated_fixture(self) -> None:
        result = self._search()
        self.assertEqual(result.validation_warnings, [])

    def test_response_time_is_measured(self) -> None:
        result = self._search()
        self.assertIsNotNone(result.response_time_ms)
        self.assertGreaterEqual(result.response_time_ms, 0)


class DemoPlatformWeek2SnapshotTests(unittest.TestCase):
    """v2.6 Milestone 2.6.4 — see docs/41_Version_2.6_Planning.md and
    fixtures/demo_platform/listings_week2.html's own comment for the exact
    three controlled changes this snapshot makes over listings.html.
    """

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_week2_snapshot_has_the_three_documented_changes(self) -> None:
        connector = DemoPlatformConnector()
        with use_demo_fixture_snapshot("week2"):
            result = connector.search(SearchRequest(location="Example City"))

        self.assertTrue(result.success)
        listings = {listing.platform_listing_id: listing for listing in result.listings}
        self.assertEqual(
            set(listings), {"demo-001", "demo-002", "demo-003", "demo-004"},
            "expected week1's 3 listings plus 1 brand-new one",
        )

        self.assertEqual(listings["demo-001"].price, 1350.0)  # was 1450.0
        self.assertEqual(listings["demo-002"].status, "unavailable")  # was "available"
        self.assertEqual(listings["demo-003"].price, 2100.0)  # unchanged control
        self.assertEqual(listings["demo-003"].status, "available")  # unchanged control
        self.assertEqual(listings["demo-004"].price, 1250.0)

    def test_snapshot_switch_is_temporary_and_scoped_to_the_with_block(self) -> None:
        connector = DemoPlatformConnector()
        with use_demo_fixture_snapshot("week2"):
            during = connector.search(SearchRequest(location="Example City"))
        after = connector.search(SearchRequest(location="Example City"))

        self.assertEqual(during.results_count, 4)
        self.assertEqual(after.results_count, 3)  # back to the permanent week1 catalog
        self.assertEqual(
            {listing.platform_listing_id for listing in after.listings},
            {"demo-001", "demo-002", "demo-003"},
        )


if __name__ == "__main__":
    unittest.main()
