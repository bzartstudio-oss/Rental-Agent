"""Unit tests for LocalDemoDataProvider — the guaranteed-always-available data
provider. `search()` is exercised for real (a real Playwright fetch of the real local
fixture, same as tests/connectors/test_demo_platform.py), under `isolated_collectors`
so nothing writes into real project data.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.providers.data.local_demo_data_provider import LocalDemoDataProvider
from src.search.search_request import SearchRequest
from tests.support import isolated_collectors


class LocalDemoDataProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = LocalDemoDataProvider()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_always_available(self) -> None:
        self.assertTrue(self.provider.is_available())

    def test_metadata_declares_this_providers_identity(self) -> None:
        metadata = self.provider.metadata()
        self.assertEqual(metadata.provider_id, "local_demo")

    def test_platform_id_is_the_real_demo_platform(self) -> None:
        self.assertEqual(self.provider.platform_id, "demo_platform")

    def test_search_returns_a_successful_result_with_the_fixture_listings(self) -> None:
        result = self.provider.search(SearchRequest(location="Example City"))

        self.assertTrue(result.success)
        self.assertEqual(result.results_count, 3)


if __name__ == "__main__":
    unittest.main()
