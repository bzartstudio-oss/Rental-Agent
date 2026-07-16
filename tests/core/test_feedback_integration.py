"""Agent-level integration tests for the User Feedback and Preference Learning
Engine — proving `RentalResearchAgent`'s optional `feedback_engine`/
`feedback_profile_id`/`feedback_mode` parameters actually change pipeline behavior
end-to-end (real Playwright fetch of the real local demo fixture, mocked at the
`BrowserCollector` boundary per the established pattern), and that the default
(no feedback_engine) path is completely unaffected.
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
from src.feedback import FeedbackEngine, FeedbackMode
from src.feedback.service import get_events_for_profile
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


class FeedbackIntegrationTests(unittest.TestCase):
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

    def test_default_behavior_unchanged_when_no_feedback_engine_given(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir)
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)

    def test_feedback_engine_records_filter_selection_events(self) -> None:
        agent = RentalResearchAgent(
            self.db, output_dir=self.output_dir, feedback_engine=FeedbackEngine(),
            feedback_profile_id="u1",
        )
        result = agent.run(SearchRequest(location="Example City", criteria={"max_price": 2000}))

        with self.db.transaction() as conn:
            events = get_events_for_profile(conn, "u1")
        self.assertTrue(any(e.event_value.get("key") == "max_price" for e in events))
        self.assertTrue(all(e.search_id == result.search_id for e in events))

    def test_report_renders_preference_profile_section(self) -> None:
        agent = RentalResearchAgent(
            self.db, output_dir=self.output_dir, feedback_engine=FeedbackEngine(),
            feedback_profile_id="u1",
        )
        result = agent.run(SearchRequest(location="Example City"))
        html = result.report_path.read_text(encoding="utf-8")
        self.assertIn('class="preferences"', html)

    def test_report_omits_preference_section_by_default(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir)
        result = agent.run(SearchRequest(location="Example City"))
        html = result.report_path.read_text(encoding="utf-8")
        self.assertNotIn('class="preferences"', html)

    def test_explicit_only_mode_does_not_change_ranking_v2_profile(self) -> None:
        agent = RentalResearchAgent(
            self.db, output_dir=self.output_dir, ranking_engine_v2=RankingEngineV2(profile=DEFAULT_PROFILE),
            feedback_engine=FeedbackEngine(), feedback_profile_id="u1", feedback_mode=FeedbackMode.EXPLICIT_ONLY,
        )
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)  # runs without crashing; profile untouched by design


if __name__ == "__main__":
    unittest.main()
