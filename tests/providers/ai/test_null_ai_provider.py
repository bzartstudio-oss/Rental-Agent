"""Unit tests for NullAIProvider — the guaranteed-always-available, honest-no-summary
AI provider."""

from __future__ import annotations

import unittest

from src.providers.ai.null_ai_provider import NullAIProvider
from src.search.search_request import SearchRequest


class NullAIProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = NullAIProvider()

    def test_always_available(self) -> None:
        self.assertTrue(self.provider.is_available())

    def test_summarize_returns_none_never_a_fabricated_string(self) -> None:
        self.assertIsNone(self.provider.summarize([], SearchRequest(location="Example City")))

    def test_metadata_has_the_lowest_quality_score(self) -> None:
        metadata = self.provider.metadata()
        self.assertEqual(metadata.provider_id, "null")
        self.assertEqual(metadata.quality_score, 0.0)


if __name__ == "__main__":
    unittest.main()
