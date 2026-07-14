import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from src.connectors.demo_platform import DemoPlatformConnector
from tests.support import isolated_collectors


def _file_uri_to_path(uri: str) -> Path:
    return Path(url2pathname(urlparse(uri).path))


class DemoPlatformConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_search_returns_all_three_fixture_listings(self) -> None:
        connector = DemoPlatformConnector()

        listings = connector.search(criteria={})

        self.assertEqual(len(listings), 3)
        self.assertEqual(
            {listing.platform_listing_id for listing in listings},
            {"demo-001", "demo-002", "demo-003"},
        )

    def test_listing_fields_are_parsed_correctly(self) -> None:
        connector = DemoPlatformConnector()

        listings = {listing.platform_listing_id: listing for listing in connector.search(criteria={})}
        studio = listings["demo-002"]

        self.assertEqual(studio.title, "Cozy Studio, Walk to Downtown")
        self.assertEqual(studio.price, 950.0)
        self.assertEqual(studio.bedrooms, 0.0)
        self.assertEqual(studio.bathrooms, 1.0)
        self.assertEqual(studio.sqft, 420.0)
        self.assertEqual(studio.address_raw, "45 Sample Avenue, Example City")
        self.assertTrue(studio.url.startswith("https://"))

    def test_image_urls_resolve_to_real_existing_files(self) -> None:
        connector = DemoPlatformConnector()

        listings = connector.search(criteria={})

        for listing in listings:
            self.assertEqual(len(listing.image_urls), 1)
            image_path = _file_uri_to_path(listing.image_urls[0])
            self.assertTrue(image_path.exists(), f"{image_path} should exist")
            self.assertTrue(image_path.read_bytes().startswith(b"\x89PNG"))

    def test_search_saves_a_raw_page_capture(self) -> None:
        connector = DemoPlatformConnector()
        connector.search(criteria={})

        captured_files = list(Path(self._tmp_dir.name).glob("raw_pages/demo_platform/*.html"))
        self.assertEqual(len(captured_files), 1)
        self.assertIn("Demo Rentals", captured_files[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
