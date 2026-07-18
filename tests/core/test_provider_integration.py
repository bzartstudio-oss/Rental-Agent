"""Agent-level integration tests for the Provider Abstraction Layer — proving
`RentalResearchAgent`'s optional `data_router`/`ai_router` parameters actually change
the pipeline's behavior end-to-end, while confirming the default (no router) path is
completely unaffected — see tests/core/test_agent.py, still passing unmodified.

`local_demo`'s underlying `DemoPlatformConnector` normally does a real Playwright
fetch (proven extensively by tests/core/test_agent.py and tests/connectors/) — this
file mocks only that one browser-launch boundary (`BrowserCollector`, reading the
real local fixture file directly instead) so these provider-routing tests aren't
coupled to real browser-launch reliability/timing, which isn't what's under test here.
RentCast's HTTP layer is mocked exactly as tests/core/test_rentcast_integration.py
already does.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from urllib.request import url2pathname

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.providers import ProviderKind, ProviderRouter
from src.search.search_request import SearchRequest
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors


def _register(db: Database, platform_id: str, connector_name: str) -> None:
    with db.transaction() as conn:
        platform_registry.register_platform(
            conn,
            Platform(
                id=platform_id,
                name=platform_id,
                country="N/A",
                homepage="local-fixture",
                connector_available=True,
                connector_name=connector_name,
                created_at=datetime.now(timezone.utc),
            ),
        )


class _FileReadingBrowser:
    """Stands in for a real `BrowserCollector`: `DemoPlatformConnector.build_url()`
    always returns a `file://` URI, so "fetching" it is just reading the file — real
    parsing/normalize logic downstream is completely unaffected.
    """

    def fetch(self, url: str, wait_ms: int = 0) -> str:
        return Path(url2pathname(urlparse(url).path)).read_text(encoding="utf-8")


@contextmanager
def _mock_browser_collector():
    with patch("src.connectors.sdk.base_connector.BrowserCollector") as mock_cls:
        mock_cls.return_value.__enter__.return_value = _FileReadingBrowser()
        yield


class ProviderIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.output_dir = Path(self._tmp_dir.name) / "output"
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()
        self._browser_cm = _mock_browser_collector()
        self._browser_cm.__enter__()
        # Both platforms the built-in data providers manage must be registered —
        # same precondition any connector already has (apartments.platform_id has a
        # real foreign key to platforms(id)).
        _register(self.db, "demo_platform", "demo_platform")
        _register(self.db, "rentcast", "rentcast")

        # v2.7 Milestone 2.7.2 — `ConnectorFactory.get(platform)` (called
        # internally by `RentalResearchAgent.run()`) constructs
        # `RentCastConnector` with no `db=` kwarg, so its lazy default (the
        # real project database) must be redirected to this test's own
        # temporary `self.db` — otherwise the rentcast-preference tests below
        # would silently write real `provider_call_budget` rows into real
        # project data.
        self._rentcast_db_patch = patch("src.connectors.rentcast.connector.Database", lambda *a, **k: self.db)
        self._rentcast_db_patch.start()

    def tearDown(self) -> None:
        self._rentcast_db_patch.stop()
        self._browser_cm.__exit__(None, None, None)
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()


class DataRouterFallbackTests(ProviderIntegrationTestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_with_no_api_key_the_router_uses_the_local_demo_provider(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, data_router=ProviderRouter(ProviderKind.DATA))
        result = agent.run(SearchRequest(location="Example City"))

        self.assertEqual(len(result.apartments), 3)  # the demo fixture's 3 listings
        for apartment in result.apartments:
            self.assertEqual(apartment.platform_id, "demo_platform")

    @patch.dict(os.environ, {"RENTCAST_API_KEY": "test-key"}, clear=True)
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_with_an_api_key_and_a_working_rentcast_the_router_prefers_rentcast(self, mock_client_cls) -> None:
        mock_client_cls.return_value.get_rental_listings.return_value = [
            {"id": "rc-1", "formattedAddress": "1 Test St", "price": 1500, "status": "Active"},
        ]
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, data_router=ProviderRouter(ProviderKind.DATA))

        result = agent.run(SearchRequest(location="Austin, TX"))

        self.assertEqual(len(result.apartments), 1)
        self.assertEqual(result.apartments[0].platform_id, "rentcast")

    @patch.dict(os.environ, {"RENTCAST_API_KEY": "test-key"}, clear=True)
    @patch("src.connectors.rentcast.connector.RentCastClient")
    def test_when_rentcast_fails_mid_run_the_router_falls_back_to_local_demo(self, mock_client_cls) -> None:
        from src.connectors.rentcast.client import RentCastClientError

        mock_client_cls.return_value.get_rental_listings.side_effect = RentCastClientError("403 forbidden")
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, data_router=ProviderRouter(ProviderKind.DATA))

        result = agent.run(SearchRequest(location="Austin, TX"))

        self.assertEqual(len(result.apartments), 3)  # fell back to the demo fixture
        for apartment in result.apartments:
            self.assertEqual(apartment.platform_id, "demo_platform")

    @patch.dict(os.environ, {}, clear=True)
    def test_default_behavior_is_unchanged_when_no_router_is_given(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir)  # no data_router at all
        result = agent.run(SearchRequest(location="Example City"))

        self.assertEqual(len(result.apartments), 3)


class AIRouterTests(ProviderIntegrationTestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_with_no_ollama_the_null_provider_produces_no_summary(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, ai_router=ProviderRouter(ProviderKind.AI))
        result = agent.run(SearchRequest(location="Example City"))

        content = result.report_path.read_text(encoding="utf-8")
        self.assertNotIn('class="ai-summary"', content)

    @patch("src.providers.ai.ollama_ai_provider.OllamaAIProvider.is_available", return_value=True)
    @patch("src.providers.ai.ollama_ai_provider.OllamaAIProvider.summarize", return_value="Three affordable listings found.")
    def test_a_working_ai_provider_adds_a_summary_to_the_report(self, mock_summarize, mock_available) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, ai_router=ProviderRouter(ProviderKind.AI))
        result = agent.run(SearchRequest(location="Example City"))

        content = result.report_path.read_text(encoding="utf-8")
        self.assertIn('class="ai-summary"', content)
        self.assertIn("Three affordable listings found.", content)

    @patch("src.providers.ai.ollama_ai_provider.OllamaAIProvider.is_available", return_value=True)
    @patch("src.providers.ai.ollama_ai_provider.OllamaAIProvider.summarize", side_effect=RuntimeError("ollama crashed"))
    def test_a_failing_ai_provider_falls_back_to_the_null_provider_not_a_crash(self, mock_summarize, mock_available) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, ai_router=ProviderRouter(ProviderKind.AI))
        result = agent.run(SearchRequest(location="Example City"))  # must not raise

        content = result.report_path.read_text(encoding="utf-8")
        self.assertNotIn('class="ai-summary"', content)  # NullAIProvider's honest None


if __name__ == "__main__":
    unittest.main()
