"""Unit tests for RentCastClient — transport concerns only (retry/backoff/timeout/auth
failure), entirely mocked at the `requests.get` boundary. No test in this module makes
a real network call, both so CI never depends on network access and so nothing here
can spend any of a real RentCast free-tier quota (see docs/20_First_Production_Connector.md).
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from src.connectors.rentcast.client import RentCastClient, RentCastClientError


def _response(status_code: int, json_body=None) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else []
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    else:
        response.raise_for_status.return_value = None
    return response


class RentCastClientSuccessTests(unittest.TestCase):
    @patch("src.connectors.rentcast.client.requests.get")
    def test_successful_request_returns_json_body(self, mock_get) -> None:
        mock_get.return_value = _response(200, [{"id": "abc"}])
        client = RentCastClient(api_key="test-key")

        result = client.get_rental_listings({"city": "Austin"})

        self.assertEqual(result, [{"id": "abc"}])
        mock_get.assert_called_once()

    @patch("src.connectors.rentcast.client.requests.get")
    def test_sends_api_key_as_header(self, mock_get) -> None:
        mock_get.return_value = _response(200, [])
        client = RentCastClient(api_key="secret-123")

        client.get_rental_listings({"city": "Austin"})

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["X-Api-Key"], "secret-123")

    @patch("src.connectors.rentcast.client.requests.get")
    def test_uses_the_real_rentcast_base_url_and_endpoint(self, mock_get) -> None:
        mock_get.return_value = _response(200, [])
        client = RentCastClient(api_key="test-key")

        client.get_rental_listings({"city": "Austin"})

        (url,), _ = mock_get.call_args
        self.assertEqual(url, "https://api.rentcast.io/v1/listings/rental/long-term")


class RentCastClientAuthFailureTests(unittest.TestCase):
    @patch("src.connectors.rentcast.client.requests.get")
    def test_401_raises_immediately_without_retrying(self, mock_get) -> None:
        mock_get.return_value = _response(401)
        client = RentCastClient(api_key="bad-key", max_retries=3)

        with self.assertRaises(RentCastClientError) as ctx:
            client.get_rental_listings({"city": "Austin"})

        self.assertIn("401", str(ctx.exception))
        mock_get.assert_called_once()  # never retried


class RentCastClientRetryTests(unittest.TestCase):
    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_server_error_retries_then_succeeds(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [_response(503), _response(200, [{"id": "x"}])]
        client = RentCastClient(api_key="test-key", max_retries=2)

        result = client.get_rental_listings({"city": "Austin"})

        self.assertEqual(result, [{"id": "x"}])
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_server_error_exhausts_retries_then_raises(self, mock_get, mock_sleep) -> None:
        mock_get.return_value = _response(500)
        client = RentCastClient(api_key="test-key", max_retries=2)

        with self.assertRaises(RentCastClientError):
            client.get_rental_listings({"city": "Austin"})

        self.assertEqual(mock_get.call_count, 3)  # initial attempt + 2 retries

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_timeout_retries_then_succeeds(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [requests.Timeout("timed out"), _response(200, [])]
        client = RentCastClient(api_key="test-key", max_retries=1)

        result = client.get_rental_listings({"city": "Austin"})

        self.assertEqual(result, [])
        self.assertEqual(mock_get.call_count, 2)

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_timeout_exhausts_retries_then_raises(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = requests.Timeout("timed out")
        client = RentCastClient(api_key="test-key", max_retries=1)

        with self.assertRaises(RentCastClientError) as ctx:
            client.get_rental_listings({"city": "Austin"})

        self.assertIn("timed out", str(ctx.exception))
        self.assertEqual(mock_get.call_count, 2)

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_connection_error_exhausts_retries_then_raises(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = requests.ConnectionError("connection refused")
        client = RentCastClient(api_key="test-key", max_retries=0)

        with self.assertRaises(RentCastClientError):
            client.get_rental_listings({"city": "Austin"})

        mock_get.assert_called_once()  # max_retries=0 means no retry at all

    @patch("src.connectors.rentcast.client.requests.get")
    def test_non_server_error_status_raises_without_retrying(self, mock_get) -> None:
        mock_get.return_value = _response(400)
        client = RentCastClient(api_key="test-key", max_retries=3)

        with self.assertRaises(RentCastClientError):
            client.get_rental_listings({"city": "Austin"})

        mock_get.assert_called_once()  # a 400 will never succeed on retry


if __name__ == "__main__":
    unittest.main()
