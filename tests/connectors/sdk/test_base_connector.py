"""Unit tests for src/connectors/sdk/base_connector.py — the BaseConnector template
method itself, using small scripted fake connectors rather than a real platform, so the
SDK's own contract is tested independently of any specific connector's parsing logic.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.connectors.base import RawListing
from src.connectors.sdk.base_connector import BaseConnector
from src.connectors.sdk.configuration import ConnectorConfiguration
from src.connectors.sdk.exceptions import ConnectorParsingError
from src.connectors.sdk.metadata import ConnectorMetadata
from src.discovery import platform_registry
from src.knowledge import knowledge_service
from src.search.search_request import SearchRequest
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors


def _make_listing(listing_id: str, **overrides) -> RawListing:
    defaults = dict(platform_listing_id=listing_id, title=f"Listing {listing_id}", price=1000.0, url=f"https://example.com/{listing_id}")
    defaults.update(overrides)
    return RawListing(**defaults)


class _ScriptedConnector(BaseConnector):
    """Overrides `fetch_listing()` entirely (skipping the real Playwright/HTTP
    transport) so `search()`'s own orchestration and error-handling can be tested in
    isolation from any real connector's fetch/parse mechanics.
    """

    platform_id = "scripted_test_connector"

    def __init__(self, config=None, *, records=None, fetch_error=None, parse_error=None, listing_ids=None) -> None:
        super().__init__(config)
        self.connected = False
        self.disconnected = False
        self._records = records if records is not None else (listing_ids or ["l1"])
        self._fetch_error = fetch_error
        self._parse_error = parse_error

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def build_url(self, request: SearchRequest) -> str:
        return "https://example.com/search"

    def fetch_listing(self, request: SearchRequest):
        if self._fetch_error:
            raise self._fetch_error
        return "raw-response"

    def parse(self, raw_response):
        if self._parse_error:
            raise self._parse_error
        return self._records

    def normalize(self, raw_record) -> RawListing:
        if isinstance(raw_record, RawListing):
            return raw_record
        return _make_listing(raw_record)

    def connector_info(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            connector_name=self.platform_id, platform_name="Scripted Test Connector",
            version="1.0.0", supports_images=True,
        )


class _DefaultFetchConnector(BaseConnector):
    """Overrides only `_collect()` — proves `fetch_listing()`'s *default*
    implementation (build_url -> _collect -> raw_page_store.save_page) without needing
    a real browser.
    """

    platform_id = "default_fetch_test_connector"

    def build_url(self, request: SearchRequest) -> str:
        return "https://example.com/search"

    def _collect(self, url: str) -> str:
        return f"<html>fetched {url}</html>"

    def parse(self, raw_response):
        return ["l1"]

    def normalize(self, raw_record) -> RawListing:
        return _make_listing(raw_record)

    def connector_info(self) -> ConnectorMetadata:
        return ConnectorMetadata(connector_name=self.platform_id, platform_name="Default Fetch Test Connector", version="1.0.0")


class SearchTemplateMethodTests(unittest.TestCase):
    def test_successful_search_returns_a_result_with_listings(self) -> None:
        connector = _ScriptedConnector(listing_ids=["l1", "l2"])
        result = connector.search(SearchRequest(location="Anywhere"))

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.results_count, 2)
        self.assertEqual({l.platform_listing_id for l in result.listings}, {"l1", "l2"})
        self.assertIsNotNone(result.response_time_ms)
        self.assertGreaterEqual(result.finished_at, result.started_at)

    def test_connect_and_disconnect_are_called(self) -> None:
        connector = _ScriptedConnector()
        connector.search(SearchRequest(location="Anywhere"))

        self.assertTrue(connector.connected)
        self.assertTrue(connector.disconnected)

    def test_disconnect_is_called_even_when_fetch_fails(self) -> None:
        connector = _ScriptedConnector(fetch_error=RuntimeError("boom"))
        connector.search(SearchRequest(location="Anywhere"))

        self.assertTrue(connector.disconnected)

    def test_an_unexpected_exception_is_wrapped_as_a_failed_result_not_raised(self) -> None:
        connector = _ScriptedConnector(fetch_error=RuntimeError("connection refused"))
        result = connector.search(SearchRequest(location="Anywhere"))

        self.assertFalse(result.success)
        self.assertEqual(result.listings, [])
        self.assertIn("connection refused", result.error)
        self.assertIn(connector.platform_id, result.error)

    def test_a_structured_connector_exception_is_preserved_not_double_wrapped(self) -> None:
        connector = _ScriptedConnector(parse_error=ConnectorParsingError("malformed page"))
        result = connector.search(SearchRequest(location="Anywhere"))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "malformed page")

    def test_validation_warnings_surface_but_do_not_fail_the_search_by_default(self) -> None:
        incomplete = _make_listing("l1", title="")
        connector = _ScriptedConnector(records=[incomplete])

        result = connector.search(SearchRequest(location="Anywhere"))

        self.assertTrue(result.success)
        self.assertEqual(len(result.validation_warnings), 1)
        self.assertEqual(result.validation_warnings[0].field, "title")

    def test_strict_validation_turns_invalid_listings_into_a_failed_result(self) -> None:
        incomplete = _make_listing("l1", title="")
        connector = _ScriptedConnector(records=[incomplete], config=ConnectorConfiguration(strict_validation=True))

        result = connector.search(SearchRequest(location="Anywhere"))

        self.assertFalse(result.success)
        self.assertIn("validation", result.error.lower())

    def test_capabilities_and_supports_reflect_connector_info(self) -> None:
        connector = _ScriptedConnector()

        self.assertTrue(connector.supports("images"))
        self.assertFalse(connector.supports("coordinates"))
        self.assertTrue(connector.capabilities().supports_images())


class DefaultFetchListingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_default_fetch_listing_builds_url_collects_and_saves_the_raw_page(self) -> None:
        connector = _DefaultFetchConnector()
        result = connector.search(SearchRequest(location="Anywhere"))

        self.assertTrue(result.success)
        captured = list(Path(self._tmp_dir.name).glob("raw_pages/default_fetch_test_connector/*.html"))
        self.assertEqual(len(captured), 1)
        self.assertIn("https://example.com/search", captured[0].read_text(encoding="utf-8"))


class HealthCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="scripted_test_connector", name="Scripted", country="Testland",
                    homepage="https://example.com", connector_available=True,
                    connector_name="scripted_test_connector", created_at=datetime.now(timezone.utc),
                ),
            )
            conn.execute(
                "INSERT INTO search_requests (id, created_at, criteria_json) VALUES (?, ?, ?)",
                ("search-1", datetime.now(timezone.utc).isoformat(), "{}"),
            )
            knowledge_service.record_platform_observation(
                conn, "scripted_test_connector", "search-1", results_count=2, failed=False,
                response_time_ms=100, raw_listings=[_make_listing("l1"), _make_listing("l2")],
                ranking_usefulness_score=1.0, parsing_success=True, observed_at=datetime.now(timezone.utc),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_health_check_delegates_to_the_knowledge_engine_for_this_platform_only(self) -> None:
        connector = _ScriptedConnector()

        with self.db.transaction() as conn:
            health = connector.health_check(conn)

        self.assertIsNotNone(health)
        self.assertEqual(health.platform_id, "scripted_test_connector")
        self.assertEqual(health.success_count, 1)
        self.assertEqual(health.failure_count, 0)

    def test_health_check_returns_none_for_a_platform_with_no_observations(self) -> None:
        connector = _DefaultFetchConnector()

        with self.db.transaction() as conn:
            health = connector.health_check(conn)

        self.assertIsNone(health)


if __name__ == "__main__":
    unittest.main()
