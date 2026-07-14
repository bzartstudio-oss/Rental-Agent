import tempfile
import unittest
from pathlib import Path

from src.connectors.demo_platform_two import DemoPlatformTwoConnector
from tests.support import isolated_collectors


class DemoPlatformTwoConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_search_returns_all_three_fixture_rows(self) -> None:
        connector = DemoPlatformTwoConnector()

        listings = connector.search(criteria={})

        self.assertEqual(len(listings), 3)
        self.assertEqual(
            {listing.platform_listing_id for listing in listings},
            {"alt-001", "alt-002", "alt-003"},
        )

    def test_table_layout_fields_are_parsed_correctly(self) -> None:
        connector = DemoPlatformTwoConnector()

        listings = {listing.platform_listing_id: listing for listing in connector.search(criteria={})}
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
