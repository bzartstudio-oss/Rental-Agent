"""Full `RentCastConnector.search()` behavior — the same entry point
`core/agent.py` calls, exercised end-to-end through `BaseConnector.search()`'s
template method (connect -> fetch_listing -> parse -> normalize -> validate). The HTTP
layer (`RentCastClient`) is mocked throughout; nothing here makes a real network call
or spends real RentCast free-tier quota.

Covers the mission's required failure scenarios: malformed listing, missing images,
missing coordinates, empty search results, and network timeout — verifying every one
of them produces a normal, inspectable `ConnectorResult` rather than a raised
exception, per `BaseConnector.search()`'s "never raises" contract.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.connectors.rentcast.client import RentCastClientError
from src.connectors.rentcast.connector import RentCastConnector
from src.search.search_request import SearchRequest
from src.storage.database import Database
from tests.support import isolated_collectors

_FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "src" / "connectors" / "rentcast" / "fixtures" / "sample_response.json"
_FIXTURES = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


class RentCastSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = patch.dict(os.environ, {"RENTCAST_API_KEY": "test-key"}, clear=True)
        self._env.__enter__()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

        # v2.7 Milestone 2.7.2 — every `RentCastConnector()` call below is
        # constructed with no arguments, so its lazy `db=None` default (the
        # real project database) must be redirected here the same way
        # `isolated_collectors` already redirects media/raw-page writes —
        # otherwise every run of this suite would silently write real
        # `provider_call_budget` rows into real project data.
        db_path = Path(self._tmp_dir.name) / "test.db"
        self._db_patch = patch(
            "src.connectors.rentcast.connector.Database",
            lambda *args, **kwargs: Database(db_path=db_path),
        )
        self._db_patch.start()

    def tearDown(self) -> None:
        self._db_patch.stop()
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()
        self._env.__exit__(None, None, None)

    def _search_with_page(self, page: list[dict]):
        connector = RentCastConnector()
        with patch("src.connectors.rentcast.connector.RentCastClient") as mock_client_cls:
            mock_client_cls.return_value.get_rental_listings.return_value = page
            return connector.search(SearchRequest(location="Austin, TX"))

    def test_successful_search_returns_normalized_listings(self) -> None:
        result = self._search_with_page(
            [_FIXTURES["full_listing"], _FIXTURES["missing_coordinates_listing"], _FIXTURES["sparse_listing"]]
        )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.platform_id, "rentcast")
        self.assertEqual(result.results_count, 3)
        self.assertIsInstance(result.response_time_ms, int)

    def test_missing_images_never_crashes_and_is_reported_honestly(self) -> None:
        result = self._search_with_page([_FIXTURES["full_listing"]])

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.listings[0].image_urls, [])

    def test_missing_coordinates_never_crashes(self) -> None:
        result = self._search_with_page([_FIXTURES["missing_coordinates_listing"]])

        self.assertTrue(result.success, result.error)
        self.assertIsNone(result.listings[0].latitude)
        self.assertIsNone(result.listings[0].longitude)

    def test_empty_search_results_is_a_success_with_zero_listings(self) -> None:
        result = self._search_with_page([])

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.results_count, 0)
        self.assertEqual(result.listings, [])

    def test_malformed_listing_produces_a_failed_result_not_a_raised_exception(self) -> None:
        result = self._search_with_page([{"status": "Active", "price": 1000}])  # no 'id'

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.listings, [])

    def test_network_timeout_produces_a_failed_result_not_a_raised_exception(self) -> None:
        connector = RentCastConnector()
        with patch("src.connectors.rentcast.connector.RentCastClient") as mock_client_cls:
            mock_client_cls.return_value.get_rental_listings.side_effect = RentCastClientError(
                "request timed out after 2 attempt(s)"
            )
            result = connector.search(SearchRequest(location="Austin, TX"))

        self.assertFalse(result.success)
        self.assertIn("timed out", result.error)
        self.assertEqual(result.listings, [])

    def test_missing_api_key_produces_a_failed_result_not_a_raised_exception(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            connector = RentCastConnector()
            result = connector.search(SearchRequest(location="Austin, TX"))

        self.assertFalse(result.success)
        self.assertIn("api key", result.error.lower())

    def test_no_validation_warnings_even_for_a_sparse_listing(self) -> None:
        result = self._search_with_page([_FIXTURES["sparse_listing"]])

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.validation_warnings, [])


if __name__ == "__main__":
    unittest.main()
