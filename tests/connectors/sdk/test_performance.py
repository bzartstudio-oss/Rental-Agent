"""Performance regression tests for the Connector SDK — registering many connectors and
repeatedly resolving/searching must stay fast as the number of installed connectors
grows (the whole point of "adding a platform requires creating only one new connector
folder": it must not make every other lookup slower).
"""

import time
import unittest
from datetime import datetime, timezone

from src.connectors.sdk.base_connector import BaseConnector
from src.connectors.sdk.factory import ConnectorFactory
from src.connectors.sdk.metadata import ConnectorMetadata
from src.connectors.sdk.registry import ConnectorRegistry, register_connector
from src.search.search_request import SearchRequest
from src.storage.models import Platform


class _BulkFakeConnector(BaseConnector):
    def build_url(self, request):
        return "https://example.com"

    def parse(self, raw_response):
        return []

    def normalize(self, raw_record):
        raise NotImplementedError

    def connector_info(self) -> ConnectorMetadata:
        return ConnectorMetadata(connector_name=self.platform_id, platform_name="Bulk Fake", version="1.0.0")


class RegistryScalePerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._registered_ids = []
        for i in range(500):
            platform_id = f"bulk_fake_connector_{i}"
            connector_class = type(f"BulkFakeConnector{i}", (_BulkFakeConnector,), {"platform_id": platform_id})
            register_connector(connector_class)
            self._registered_ids.append(platform_id)

    def tearDown(self) -> None:
        for platform_id in self._registered_ids:
            ConnectorRegistry._connectors.pop(platform_id, None)

    def test_registry_lookup_stays_fast_with_hundreds_of_connectors(self) -> None:
        started = time.perf_counter()
        for platform_id in self._registered_ids:
            ConnectorRegistry.get(platform_id)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 1.0)

    def test_factory_resolution_stays_fast_with_hundreds_of_connectors(self) -> None:
        platforms = [
            Platform(
                id=platform_id, name=platform_id, country="Testland", homepage="https://example.com",
                connector_available=True, connector_name=platform_id, created_at=datetime.now(timezone.utc),
            )
            for platform_id in self._registered_ids
        ]

        started = time.perf_counter()
        for platform in platforms:
            ConnectorFactory.get(platform)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 1.0)


class SearchTemplateMethodPerformanceTests(unittest.TestCase):
    def test_repeated_searches_against_a_lightweight_connector_stay_fast(self) -> None:
        from tests.connectors.sdk.test_base_connector import _ScriptedConnector

        connector = _ScriptedConnector(listing_ids=[f"l{i}" for i in range(50)])
        request = SearchRequest(location="Anywhere")

        started = time.perf_counter()
        for _ in range(200):
            result = connector.search(request)
            self.assertTrue(result.success)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
