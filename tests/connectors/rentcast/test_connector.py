"""Unit tests for RentCastConnector's own hooks (connect/build_url/parse/normalize/
connector_info) plus fetch_listing's pagination — everything except the actual HTTP
call, which is `RentCastClient`'s job and already covered by test_client.py. Nothing
here makes a real network call.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.connectors.rentcast import budget
from src.connectors.rentcast.client import RentCastClientError
from src.connectors.rentcast.connector import RentCastConnector
from src.connectors.sdk.configuration import ConnectorConfiguration
from src.connectors.sdk.exceptions import (
    ConnectorConfigurationError,
    ConnectorConnectionError,
    ConnectorParsingError,
)
from src.search.search_request import SearchRequest
from src.storage.database import Database

_FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "src" / "connectors" / "rentcast" / "fixtures" / "sample_response.json"
_FIXTURES = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


class ConnectTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_raises_configuration_error_with_no_credentials_anywhere(self) -> None:
        connector = RentCastConnector()
        with self.assertRaises(ConnectorConfigurationError):
            connector.connect()

    @patch.dict(os.environ, {}, clear=True)
    def test_uses_configured_credentials(self) -> None:
        connector = RentCastConnector(ConnectorConfiguration(credentials={"api_key": "from-config"}))
        connector.connect()
        self.assertEqual(connector._api_key, "from-config")

    @patch.dict(os.environ, {"RENTCAST_API_KEY": "from-env"}, clear=True)
    def test_falls_back_to_environment_variable(self) -> None:
        connector = RentCastConnector()
        connector.connect()
        self.assertEqual(connector._api_key, "from-env")

    @patch.dict(os.environ, {"RENTCAST_API_KEY": "from-env"}, clear=True)
    def test_configured_credentials_take_priority_over_environment(self) -> None:
        connector = RentCastConnector(ConnectorConfiguration(credentials={"api_key": "from-config"}))
        connector.connect()
        self.assertEqual(connector._api_key, "from-config")


class BuildUrlTests(unittest.TestCase):
    def test_returns_the_real_rentcast_endpoint(self) -> None:
        connector = RentCastConnector()
        url = connector.build_url(SearchRequest(location="Austin, TX"))
        self.assertEqual(url, "https://api.rentcast.io/v1/listings/rental/long-term")


class ParseTests(unittest.TestCase):
    def test_parse_is_passthrough(self) -> None:
        connector = RentCastConnector()
        records = [_FIXTURES["full_listing"]]
        self.assertIs(connector.parse(records), records)


class NormalizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = RentCastConnector()

    def test_full_listing_maps_every_available_field(self) -> None:
        listing = self.connector.normalize(_FIXTURES["full_listing"])

        self.assertEqual(listing.platform_listing_id, "123-Sample-St,-Austin,-TX-78701")
        self.assertEqual(listing.title, "123 Sample St, Austin, TX 78701")
        self.assertEqual(listing.price, 2100.0)
        self.assertEqual(
            listing.url,
            "https://api.rentcast.io/v1/listings/rental/long-term/123-Sample-St,-Austin,-TX-78701",
        )
        self.assertEqual(listing.bedrooms, 2)
        self.assertEqual(listing.bathrooms, 2)
        self.assertEqual(listing.sqft, 950)
        self.assertEqual(listing.address_raw, "123 Sample St, Austin, TX 78701")
        self.assertEqual(listing.status, "available")
        self.assertEqual(listing.latitude, 30.267153)
        self.assertEqual(listing.longitude, -97.743057)
        self.assertEqual(listing.currency, "USD")
        self.assertEqual(listing.property_type, "Apartment")
        # Honest gaps in RentCast's schema — never fabricated.
        self.assertEqual(listing.image_urls, [])
        self.assertIsNone(listing.description)

    def test_missing_coordinates_listing_normalizes_with_none_coordinates(self) -> None:
        listing = self.connector.normalize(_FIXTURES["missing_coordinates_listing"])

        self.assertIsNone(listing.latitude)
        self.assertIsNone(listing.longitude)
        self.assertEqual(listing.bedrooms, 3)
        self.assertEqual(listing.price, 1800.0)

    def test_sparse_listing_normalizes_without_crashing(self) -> None:
        listing = self.connector.normalize(_FIXTURES["sparse_listing"])

        self.assertEqual(listing.platform_listing_id, "789-Minimal-Rd,-Austin,-TX-78703")
        self.assertEqual(listing.title, "789-Minimal-Rd,-Austin,-TX-78703")  # falls back to id
        self.assertEqual(listing.price, 1500.0)
        self.assertIsNone(listing.bedrooms)
        self.assertIsNone(listing.bathrooms)
        self.assertIsNone(listing.sqft)
        self.assertIsNone(listing.address_raw)
        self.assertIsNone(listing.latitude)
        self.assertIsNone(listing.longitude)
        self.assertIsNone(listing.property_type)
        self.assertEqual(listing.image_urls, [])
        self.assertIsNone(listing.description)

    def test_malformed_listing_missing_id_raises_parsing_error(self) -> None:
        with self.assertRaises(ConnectorParsingError):
            self.connector.normalize({"status": "Active", "price": 1000})

    def test_missing_price_defaults_to_zero_rather_than_crashing(self) -> None:
        listing = self.connector.normalize({"id": "no-price-1"})
        self.assertEqual(listing.price, 0.0)


class ConnectorInfoTests(unittest.TestCase):
    def test_declares_expected_capabilities(self) -> None:
        metadata = RentCastConnector().connector_info()

        self.assertEqual(metadata.connector_name, "rentcast")
        self.assertFalse(metadata.supports_images)  # RentCast's schema has no photos
        self.assertTrue(metadata.supports_availability)
        self.assertTrue(metadata.supports_coordinates)
        self.assertTrue(metadata.supports_pagination)


class FetchListingPaginationTests(unittest.TestCase):
    """v2.7 Milestone 2.7.2 — `fetch_listing()` now gates each page on the
    monthly call budget, which reads/writes a real table, so this suite (like
    the new budget-specific tests) points the connector at a temporary
    database rather than `db=None`'s production default (the real project
    database) — the same test-isolation discipline every other engine's own
    test suite already follows.
    """

    def setUp(self) -> None:
        self._tmp_env = patch.dict(os.environ, {"RENTCAST_API_KEY": "test-key"}, clear=True)
        self._tmp_env.__enter__()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.connector = RentCastConnector(db=self.db)
        self.connector.connect()

    def tearDown(self) -> None:
        self._tmp_env.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    @patch("src.connectors.rentcast.connector.raw_page_store")
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_stops_pagination_on_a_short_page(self, mock_client_cls, mock_raw_store) -> None:
        mock_client_cls.return_value.get_rental_listings.return_value = [{"id": "1"}, {"id": "2"}]

        records = self.connector.fetch_listing(SearchRequest(location="Austin, TX"))

        self.assertEqual(records, [{"id": "1"}, {"id": "2"}])
        mock_client_cls.return_value.get_rental_listings.assert_called_once()

    @patch("src.connectors.rentcast.connector.raw_page_store")
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_empty_first_page_returns_empty_list_without_crashing(self, mock_client_cls, mock_raw_store) -> None:
        mock_client_cls.return_value.get_rental_listings.return_value = []

        records = self.connector.fetch_listing(SearchRequest(location="Austin, TX"))

        self.assertEqual(records, [])

    @patch("src.connectors.rentcast.connector.raw_page_store")
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_stops_at_max_pages_even_if_every_page_is_full(self, mock_client_cls, mock_raw_store) -> None:
        full_page = [{"id": str(i)} for i in range(100)]
        mock_client_cls.return_value.get_rental_listings.return_value = full_page

        records = self.connector.fetch_listing(SearchRequest(location="Austin, TX"))

        self.assertEqual(mock_client_cls.return_value.get_rental_listings.call_count, 3)  # _MAX_PAGES
        self.assertEqual(len(records), 300)

    @patch("src.connectors.rentcast.connector.raw_page_store")
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_saves_a_raw_capture_of_every_page_combined(self, mock_client_cls, mock_raw_store) -> None:
        mock_client_cls.return_value.get_rental_listings.return_value = [{"id": "1"}]

        self.connector.fetch_listing(SearchRequest(location="Austin, TX"))

        mock_raw_store.save_page.assert_called_once()
        args, kwargs = mock_raw_store.save_page.call_args
        self.assertEqual(args[0], "rentcast")
        self.assertEqual(kwargs.get("suffix") or (args[2] if len(args) > 2 else None), "json")

    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_client_error_is_wrapped_as_connector_connection_error(self, mock_client_cls) -> None:
        mock_client_cls.return_value.get_rental_listings.side_effect = RentCastClientError("network is down")

        with self.assertRaises(ConnectorConnectionError):
            self.connector.fetch_listing(SearchRequest(location="Austin, TX"))


class FetchListingCallBudgetTests(unittest.TestCase):
    """v2.7 Milestone 2.7.2 — `fetch_listing()`'s call-budget guard."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _connector(self) -> RentCastConnector:
        connector = RentCastConnector(db=self.db)
        connector._api_key = "test-key"  # bypass connect() — not under test here
        return connector

    @patch.dict(os.environ, {"RENTCAST_MONTHLY_CALL_BUDGET": "1"}, clear=True)
    @patch("src.connectors.rentcast.connector.raw_page_store")
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_raises_when_budget_is_exhausted_before_the_first_page(self, mock_client_cls, mock_raw_store) -> None:
        connector = self._connector()
        # Exhaust the budget (limit=1) before this connector ever calls fetch_listing.
        with self.db.transaction() as conn:
            budget.try_consume_call(conn, "rentcast", monthly_limit=1, now=datetime.now(timezone.utc))

        with self.assertRaises(ConnectorConnectionError) as ctx:
            connector.fetch_listing(SearchRequest(location="Austin, TX"))

        self.assertIn("budget", str(ctx.exception).lower())
        mock_client_cls.return_value.get_rental_listings.assert_not_called()

    @patch.dict(os.environ, {"RENTCAST_MONTHLY_CALL_BUDGET": "2"}, clear=True)
    @patch("src.connectors.rentcast.connector.raw_page_store")
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_returns_partial_results_when_budget_runs_out_mid_pagination(self, mock_client_cls, mock_raw_store) -> None:
        full_page = [{"id": str(i)} for i in range(100)]  # a full page, so pagination would otherwise continue
        mock_client_cls.return_value.get_rental_listings.return_value = full_page
        connector = self._connector()

        records = connector.fetch_listing(SearchRequest(location="Austin, TX"))

        # Budget of 2 permits exactly 2 page requests (200 records), then stops
        # gracefully instead of raising, even though a 3rd page would otherwise be fetched.
        self.assertEqual(mock_client_cls.return_value.get_rental_listings.call_count, 2)
        self.assertEqual(len(records), 200)

    @patch.dict(os.environ, {"RENTCAST_MONTHLY_CALL_BUDGET": "3"}, clear=True)
    @patch("src.connectors.rentcast.connector.raw_page_store")
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_a_search_within_budget_succeeds_normally(self, mock_client_cls, mock_raw_store) -> None:
        mock_client_cls.return_value.get_rental_listings.return_value = [{"id": "1"}]
        connector = self._connector()

        records = connector.fetch_listing(SearchRequest(location="Austin, TX"))

        self.assertEqual(records, [{"id": "1"}])

    @patch.dict(os.environ, {}, clear=True)
    @patch("src.connectors.rentcast.connector.raw_page_store")
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_defaults_to_the_free_tier_budget_when_unconfigured(self, mock_client_cls, mock_raw_store) -> None:
        connector = self._connector()
        self.assertEqual(connector._monthly_call_budget(), 50)

    @patch.dict(os.environ, {"RENTCAST_MONTHLY_CALL_BUDGET": "not-a-number"}, clear=True)
    def test_unparseable_budget_env_var_falls_back_to_the_default(self) -> None:
        connector = self._connector()
        self.assertEqual(connector._monthly_call_budget(), 50)


if __name__ == "__main__":
    unittest.main()
