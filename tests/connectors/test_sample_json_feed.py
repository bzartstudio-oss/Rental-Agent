"""Tests for SampleJsonFeedConnector — the third reference connector built for the
SDK Validation Sprint (docs/22_SDK_Validation_Sprint.md). Two concerns beyond the
usual per-connector tests: proving the factory discovers it automatically purely by
naming convention (no registry/known_platforms.py edit anywhere), and stress-testing
RawListing/Apartment field coverage against a deliberately different JSON shape.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from src.connectors.sdk.exceptions import ConnectorConfigurationError
from src.connectors.sdk.factory import ConnectorFactory
from src.connectors.sdk.registry import ConnectorRegistry
from src.search.search_request import SearchRequest
from src.storage.models import Platform
from tests.connectors.sdk.certification import ConnectorCertificationMixin
from tests.support import isolated_collectors


def _file_uri_to_path(uri: str) -> Path:
    return Path(url2pathname(urlparse(uri).path))


def _platform() -> Platform:
    """Constructed directly, never read from `discovery/known_platforms.py` — this
    connector is deliberately not seeded there (see connector.py's module docstring).
    """
    return Platform(
        id="sample_json_feed",
        name="Sample JSON Feed",
        country="N/A",
        homepage="local-fixture",
        connector_available=True,
        connector_name="sample_json_feed",
    )


class AutoDiscoveryTests(unittest.TestCase):
    """Directly validates "does the factory discover connectors automatically?" —
    the registry must resolve this connector purely from `Platform.connector_name`,
    with no prior import anywhere in this test and no entry in
    `discovery/known_platforms.py`.

    `setUp` forces a genuinely "never imported" state regardless of what any other
    test module elsewhere in the suite already did — this connector is otherwise
    real, permanent, and other test classes in this same file do legitimately import
    it, so this test can't just rely on being first.
    """

    def setUp(self) -> None:
        ConnectorRegistry._connectors.pop("sample_json_feed", None)
        sys.modules.pop("src.connectors.sample_json_feed", None)
        sys.modules.pop("src.connectors.sample_json_feed.connector", None)

    def test_factory_resolves_a_never_before_imported_connector_by_name_alone(self) -> None:
        self.assertFalse(ConnectorRegistry.is_registered("sample_json_feed"))

        # A genuinely unknown connector_name still raises the SDK's own structured
        # error, not a bare ImportError/KeyError — confirms the lookup path is real,
        # not a hardcoded special case for "sample_json_feed".
        unknown = Platform(
            id="does_not_exist", name="x", country="N/A", homepage="x",
            connector_available=True, connector_name="definitely_not_a_real_connector",
        )
        with self.assertRaises(ConnectorConfigurationError):
            ConnectorFactory.get(unknown)

        # The real connector, looked up for the first time by this test process,
        # resolves without ever being imported by name anywhere above.
        connector = ConnectorFactory.get(_platform())
        self.assertTrue(ConnectorRegistry.is_registered("sample_json_feed"))
        self.assertIs(ConnectorRegistry.get("sample_json_feed"), type(connector))


class SampleJsonFeedCertificationTests(ConnectorCertificationMixin, unittest.TestCase):
    connector_class = None  # set in setUp, after ConnectorFactory has resolved it once
    search_request = SearchRequest(location="Sample City")

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()
        SampleJsonFeedCertificationTests.connector_class = type(ConnectorFactory.get(_platform()))

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()


class SampleJsonFeedConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def _search(self):
        connector = ConnectorFactory.get(_platform())
        return connector.search(SearchRequest(location="Sample City"))

    def test_search_returns_a_successful_result_with_both_fixture_listings(self) -> None:
        result = self._search()

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.results_count, 2)
        self.assertEqual(
            {listing.platform_listing_id for listing in result.listings},
            {"feed-001", "feed-002"},
        )

    def test_full_field_coverage_for_a_richly_populated_listing(self) -> None:
        result = self._search()
        listing = next(l for l in result.listings if l.platform_listing_id == "feed-001")

        self.assertEqual(listing.title, "Sunny One-Bedroom Near the Park")
        self.assertEqual(listing.price, 1650.0)
        self.assertEqual(listing.bedrooms, 1)
        self.assertEqual(listing.bathrooms, 1)
        self.assertEqual(listing.sqft, 620)
        self.assertEqual(listing.address_raw, "12 Feed Lane, Sample City")
        self.assertEqual(listing.status, "available")
        self.assertEqual(listing.description, "A bright one-bedroom two blocks from the park, recently repainted.")
        self.assertAlmostEqual(listing.latitude, 40.7128)
        self.assertAlmostEqual(listing.longitude, -74.0060)
        self.assertEqual(listing.currency, "USD")
        self.assertEqual(listing.property_type, "apartment")
        self.assertEqual(len(listing.image_urls), 1)
        image_path = _file_uri_to_path(listing.image_urls[0])
        self.assertTrue(image_path.exists())
        self.assertTrue(image_path.read_bytes().startswith(b"\x89PNG"))

    def test_missing_optional_fields_normalize_without_crashing(self) -> None:
        result = self._search()
        listing = next(l for l in result.listings if l.platform_listing_id == "feed-002")

        self.assertIsNone(listing.description)  # fixture's summary is null
        self.assertEqual(listing.image_urls, [])  # fixture's photo_urls is empty

    def test_search_saves_a_raw_page_capture(self) -> None:
        self._search()

        captured_files = list(Path(self._tmp_dir.name).glob("raw_pages/sample_json_feed/*.html"))
        self.assertEqual(len(captured_files), 1)
        self.assertIn("feed-001", captured_files[0].read_text(encoding="utf-8"))

    def test_no_validation_warnings_for_the_fixture(self) -> None:
        result = self._search()
        self.assertEqual(result.validation_warnings, [])


if __name__ == "__main__":
    unittest.main()
