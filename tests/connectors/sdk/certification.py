"""Not a test module itself (no `test_` prefix — `unittest discover` skips it).

`ConnectorCertificationMixin` — mix this into any connector's own test case to certify
it meets the SDK contract, per docs/18_Connector_SDK.md "Certification Requirements".
A brand-new connector inherits this for free the same way it inherits `BaseConnector`'s
behavior: implement `build_url`/`parse`/`normalize`/`connector_info` correctly, and
these checks pass without any certification-specific code in the connector itself.

Usage — see tests/connectors/test_demo_platform.py for the real example:

    class MyConnectorTests(ConnectorCertificationMixin, unittest.TestCase):
        connector_class = MyConnector
        search_request = SearchRequest(location="Some City")

        def setUp(self):
            self._collectors_cm = isolated_collectors(...)
            self._collectors_cm.__enter__()
        ...
"""

from __future__ import annotations

from src.connectors.sdk.base_connector import BaseConnector
from src.connectors.sdk.metadata import ConnectorMetadata
from src.connectors.sdk.registry import ConnectorRegistry
from src.connectors.sdk.result import ConnectorResult
from src.search.search_request import SearchRequest


class ConnectorCertificationMixin:
    """Set `connector_class` and `search_request` as class attributes on the test case
    mixing this in. Requires a real, working fetch (real Playwright/HTTP call) — run
    these under the same `isolated_collectors` protection every real-connector test
    already uses, so nothing writes into real project data.
    """

    connector_class: type[BaseConnector]
    search_request: SearchRequest = SearchRequest(location="Certification Test City")

    def test_certification_platform_id_is_set(self) -> None:
        self.assertTrue(self.connector_class.platform_id)

    def test_certification_is_self_registered(self) -> None:
        self.assertTrue(ConnectorRegistry.is_registered(self.connector_class.platform_id))
        self.assertIs(ConnectorRegistry.get(self.connector_class.platform_id), self.connector_class)

    def test_certification_declares_valid_metadata(self) -> None:
        connector = self.connector_class()
        metadata = connector.connector_info()

        self.assertIsInstance(metadata, ConnectorMetadata)
        self.assertEqual(metadata.connector_name, self.connector_class.platform_id)
        self.assertTrue(metadata.platform_name)
        self.assertTrue(metadata.version)

    def test_certification_capabilities_are_queryable_without_raising(self) -> None:
        connector = self.connector_class()
        for capability in ("images", "availability", "coordinates", "pagination", "login"):
            self.assertIsInstance(connector.supports(capability), bool)

    def test_certification_search_returns_a_connector_result(self) -> None:
        connector = self.connector_class()
        result = connector.search(self.search_request)

        self.assertIsInstance(result, ConnectorResult)
        self.assertEqual(result.platform_id, self.connector_class.platform_id)
        self.assertTrue(result.success, f"search() failed: {result.error}")
        self.assertIsInstance(result.results_count, int)

    def test_certification_every_listing_is_a_valid_raw_listing(self) -> None:
        connector = self.connector_class()
        result = connector.search(self.search_request)

        for listing in result.listings:
            self.assertTrue(listing.platform_listing_id)
            self.assertTrue(listing.title)
            self.assertTrue(listing.url)
