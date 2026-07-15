"""Unit tests for RentCastDataProvider — the Provider-layer adapter over
RentCastConnector (v2.0 Step 7). Only this adapter's own logic (is_available/metadata/
delegation) is tested here; RentCastConnector's own behavior is already covered by
tests/connectors/rentcast/.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.providers.data.rentcast_data_provider import RentCastDataProvider


class RentCastDataProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = RentCastDataProvider()

    @patch.dict(os.environ, {}, clear=True)
    def test_unavailable_without_an_api_key(self) -> None:
        self.assertFalse(self.provider.is_available())

    @patch.dict(os.environ, {"RENTCAST_API_KEY": "a-real-key"}, clear=True)
    def test_available_with_an_api_key(self) -> None:
        self.assertTrue(self.provider.is_available())

    def test_metadata_declares_this_providers_identity(self) -> None:
        metadata = self.provider.metadata()
        self.assertEqual(metadata.provider_id, "rentcast")
        self.assertTrue(0.0 <= metadata.cost_score <= 1.0)
        self.assertTrue(0.0 <= metadata.freshness_score <= 1.0)
        self.assertTrue(0.0 <= metadata.quality_score <= 1.0)

    def test_platform_id_matches_the_real_registered_platform(self) -> None:
        self.assertEqual(self.provider.platform_id, "rentcast")

    @patch("src.providers.data.rentcast_data_provider.ConnectorFactory")
    def test_search_delegates_to_connector_factory(self, mock_factory) -> None:
        from src.search.search_request import SearchRequest

        mock_connector = mock_factory.get.return_value
        mock_connector.search.return_value = "a-connector-result"
        request = SearchRequest(location="Austin, TX")

        result = self.provider.search(request)

        self.assertEqual(result, "a-connector-result")
        mock_factory.get.assert_called_once()
        (platform_arg,), _ = mock_factory.get.call_args
        self.assertEqual(platform_arg.id, "rentcast")
        self.assertEqual(platform_arg.connector_name, "rentcast")
        mock_connector.search.assert_called_once_with(request)


if __name__ == "__main__":
    unittest.main()
