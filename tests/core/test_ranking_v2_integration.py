"""Agent-level integration tests for the Intelligent Ranking Engine V2 — proving
`RentalResearchAgent`'s optional `ranking_engine_v2` parameter actually changes
pipeline behavior end-to-end (real Playwright fetch of the real local demo fixture,
mocked at the `BrowserCollector` boundary per
`tests/core/test_filter_engine_integration.py`'s own precedent), and that the
default (no ranking_engine_v2) path is completely unaffected.
"""

from __future__ import annotations

import contextlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from urllib.request import url2pathname

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.ranking_v2 import DEFAULT_PROFILE, RankingEngineV2
from src.search.search_request import SearchRequest
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors


class _FileReadingBrowser:
    def fetch(self, url: str, wait_ms: int = 0) -> str:
        return Path(url2pathname(urlparse(url).path)).read_text(encoding="utf-8")


@contextlib.contextmanager
def _mock_browser_collector():
    with patch("src.connectors.sdk.base_connector.BrowserCollector") as mock_cls:
        mock_cls.return_value.__enter__.return_value = _FileReadingBrowser()
        yield


class RankingV2IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.output_dir = Path(self._tmp_dir.name) / "output"
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()
        self._browser_cm = _mock_browser_collector()
        self._browser_cm.__enter__()

        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform", name="Demo Platform", country="N/A", homepage="local-fixture",
                    connector_available=True, connector_name="demo_platform",
                    created_at=datetime.now(timezone.utc),
                ),
            )

    def tearDown(self) -> None:
        self._browser_cm.__exit__(None, None, None)
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_default_behavior_unchanged_when_no_ranking_engine_v2_given(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir)  # no ranking_engine_v2
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)

    def test_ranking_engine_v2_runs_without_crashing(self) -> None:
        agent = RentalResearchAgent(
            self.db, output_dir=self.output_dir, ranking_engine_v2=RankingEngineV2(profile=DEFAULT_PROFILE),
        )
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)  # v1 hard-filtering/candidate set unaffected

    def test_report_renders_the_ranking_v2_section(self) -> None:
        agent = RentalResearchAgent(
            self.db, output_dir=self.output_dir, ranking_engine_v2=RankingEngineV2(profile=DEFAULT_PROFILE),
        )
        result = agent.run(SearchRequest(location="Example City"))
        html = result.report_path.read_text(encoding="utf-8")
        self.assertIn('class="ranking-v2"', html)
        self.assertIn("Ranking Engine V2 — Score:", html)

    def test_report_omits_the_ranking_v2_section_by_default(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir)  # no ranking_engine_v2
        result = agent.run(SearchRequest(location="Example City"))
        html = result.report_path.read_text(encoding="utf-8")
        self.assertNotIn('class="ranking-v2"', html)


if __name__ == "__main__":
    unittest.main()
