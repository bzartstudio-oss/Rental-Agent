"""Unit tests for RentCastClient — transport concerns only (retry/backoff/timeout/auth
failure), entirely mocked at the `requests.get` boundary. No test in this module makes
a real network call, both so CI never depends on network access and so nothing here
can spend any of a real RentCast free-tier quota (see docs/20_First_Production_Connector.md).
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from src.connectors.rentcast.client import RentCastClient, RentCastClientError, RentCastRateLimitError


def _response(status_code: int, json_body=None, headers: dict | None = None) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else []
    response.headers = headers if headers is not None else {}
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


class RentCastClientRateLimitTests(unittest.TestCase):
    """v2.7 Milestone 2.7.2 — explicit 429 handling, distinct from the
    generic 5xx path. No test here makes a real network call or sleeps for
    real (`time.sleep` is always mocked), matching every other test in this
    module.
    """

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_429_with_retry_after_seconds_waits_the_exact_value_then_succeeds(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [
            _response(429, headers={"Retry-After": "7"}),
            _response(200, [{"id": "x"}]),
        ]
        client = RentCastClient(api_key="test-key", max_retries=1)

        result = client.get_rental_listings({"city": "Austin"})

        self.assertEqual(result, [{"id": "x"}])
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(7.0)

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_429_with_retry_after_above_the_cap_is_clamped(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [
            _response(429, headers={"Retry-After": "3600"}),
            _response(200, []),
        ]
        client = RentCastClient(api_key="test-key", max_retries=1)

        client.get_rental_listings({"city": "Austin"})

        mock_sleep.assert_called_once_with(60.0)  # _MAX_RETRY_AFTER_SECONDS

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_429_without_retry_after_falls_back_to_exponential_backoff(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [_response(429), _response(200, [])]
        client = RentCastClient(api_key="test-key", max_retries=1)

        client.get_rental_listings({"city": "Austin"})

        mock_sleep.assert_called_once_with(0.5)  # _BACKOFF_BASE_SECONDS * 2**0

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_429_with_unparseable_retry_after_falls_back_to_exponential_backoff(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [_response(429, headers={"Retry-After": "not-a-number"}), _response(200, [])]
        client = RentCastClient(api_key="test-key", max_retries=1)

        client.get_rental_listings({"city": "Austin"})

        mock_sleep.assert_called_once_with(0.5)

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_429_exhausts_retries_then_raises_rate_limit_error(self, mock_get, mock_sleep) -> None:
        mock_get.return_value = _response(429, headers={"Retry-After": "1"})
        client = RentCastClient(api_key="test-key", max_retries=2)

        with self.assertRaises(RentCastRateLimitError):
            client.get_rental_listings({"city": "Austin"})

        self.assertEqual(mock_get.call_count, 3)  # initial attempt + 2 retries

    @patch("src.connectors.rentcast.client.requests.get")
    def test_429_with_zero_max_retries_raises_immediately(self, mock_get) -> None:
        mock_get.return_value = _response(429, headers={"Retry-After": "1"})
        client = RentCastClient(api_key="test-key", max_retries=0)

        with self.assertRaises(RentCastRateLimitError):
            client.get_rental_listings({"city": "Austin"})

        mock_get.assert_called_once()

    def test_rate_limit_error_is_a_client_error_subclass(self) -> None:
        """Existing callers catching the parent `RentCastClientError` (e.g.
        `RentCastConnector.fetch_listing()`) need no change to also handle 429.
        """
        self.assertTrue(issubclass(RentCastRateLimitError, RentCastClientError))

    @patch("src.connectors.rentcast.client.time.sleep")
    @patch("src.connectors.rentcast.client.requests.get")
    def test_api_key_never_appears_in_logs_during_a_429_retry(self, mock_get, mock_sleep) -> None:
        mock_get.side_effect = [
            _response(429, headers={"Retry-After": "2"}),
            _response(200, []),
        ]
        client = RentCastClient(api_key="super-secret-key-value", max_retries=1)

        with self.assertLogs("src.connectors.rentcast.client", level="WARNING") as captured:
            client.get_rental_listings({"city": "Austin"})

        joined = "\n".join(captured.output)
        self.assertNotIn("super-secret-key-value", joined)


if __name__ == "__main__":
    unittest.main()
