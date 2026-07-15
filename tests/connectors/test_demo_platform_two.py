"""v2.0 Step 5: DemoPlatformTwoConnector rebuilt on BaseConnector — see
test_demo_platform.py's docstring for the interface-change rationale.
"""

import tempfile
import unittest
from pathlib import Path

from src.connectors.demo_platform_two import DemoPlatformTwoConnector
from src.search.search_request import SearchRequest
from tests.connectors.sdk.certification import ConnectorCertificationMixin
from tests.support import isolated_collectors


class DemoPlatformTwoConnectorCertificationTests(ConnectorCertificationMixin, unittest.TestCase):
    connector_class = DemoPlatformTwoConnector
    search_request = SearchRequest(location="Example City")

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()


class DemoPlatformTwoConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def _search(self):
        connector = DemoPlatformTwoConnector()
        return connector.search(SearchRequest(location="Example City"))

    def test_search_returns_a_successful_result_with_all_three_fixture_rows(self) -> None:
        result = self._search()

        self.assertTrue(result.success)
        self.assertEqual(result.results_count, 3)
        self.assertEqual(
            {listing.platform_listing_id for listing in result.listings},
            {"alt-001", "alt-002", "alt-003"},
        )

    def test_table_layout_fields_are_parsed_correctly(self) -> None:
        result = self._search()
        listings = {listing.platform_listing_id: listing for listing in result.listings}
        loft = listings["alt-001"]

        self.assertEqual(loft.title, "Modern 1BR Loft")
        self.assertEqual(loft.price, 1100.0)
        self.assertEqual(loft.bedrooms, 1.0)
        self.assertEqual(loft.bathrooms, 1.0)
        self.assertEqual(loft.sqft, 600.0)
        self.assertEqual(loft.address_raw, "88 Second Avenue, Example City")
        self.assertEqual(len(loft.image_urls), 1)


if __name__ == "__main__":
    unittest.main()
