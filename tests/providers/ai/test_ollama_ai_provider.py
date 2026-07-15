"""Unit tests for OllamaAIProvider — entirely mocked at the `requests` boundary; no
test here makes a real network call or requires a real local Ollama install.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from src.providers.ai.ollama_ai_provider import OllamaAIProvider, OllamaAIProviderError
from src.search.search_request import SearchRequest


class OllamaAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OllamaAIProvider()

    @patch("src.providers.ai.ollama_ai_provider.requests.get")
    def test_available_when_the_local_server_responds_200(self, mock_get) -> None:
        mock_get.return_value = Mock(status_code=200)
        self.assertTrue(self.provider.is_available())

    @patch("src.providers.ai.ollama_ai_provider.requests.get")
    def test_unavailable_on_non_200_response(self, mock_get) -> None:
        mock_get.return_value = Mock(status_code=500)
        self.assertFalse(self.provider.is_available())

    @patch("src.providers.ai.ollama_ai_provider.requests.get")
    def test_unavailable_when_connection_refused(self, mock_get) -> None:
        mock_get.side_effect = requests.ConnectionError("refused")
        self.assertFalse(self.provider.is_available())

    @patch("src.providers.ai.ollama_ai_provider.requests.get")
    def test_unavailable_on_timeout(self, mock_get) -> None:
        mock_get.side_effect = requests.Timeout("timed out")
        self.assertFalse(self.provider.is_available())


class OllamaSummarizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OllamaAIProvider()
        self.request = SearchRequest(location="Austin, TX")

    @patch("src.providers.ai.ollama_ai_provider.requests.post")
    def test_returns_the_models_response_text(self, mock_post) -> None:
        mock_post.return_value = Mock(status_code=200, json=lambda: {"response": "  A nice summary.  "})
        mock_post.return_value.raise_for_status.return_value = None

        summary = self.provider.summarize([], self.request)

        self.assertEqual(summary, "A nice summary.")

    @patch("src.providers.ai.ollama_ai_provider.requests.post")
    def test_returns_none_for_an_empty_response(self, mock_post) -> None:
        mock_post.return_value = Mock(status_code=200, json=lambda: {"response": ""})
        mock_post.return_value.raise_for_status.return_value = None

        self.assertIsNone(self.provider.summarize([], self.request))

    @patch("src.providers.ai.ollama_ai_provider.requests.post")
    def test_raises_ollama_error_on_request_failure(self, mock_post) -> None:
        mock_post.side_effect = requests.ConnectionError("refused")

        with self.assertRaises(OllamaAIProviderError):
            self.provider.summarize([], self.request)

    def test_metadata_declares_this_providers_identity(self) -> None:
        metadata = self.provider.metadata()
        self.assertEqual(metadata.provider_id, "ollama")


if __name__ == "__main__":
    unittest.main()
