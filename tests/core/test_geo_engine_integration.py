"""Agent-level integration tests for the Geographic Intelligence Engine — proving
`RentalResearchAgent`'s optional `geo_engine` parameter actually changes pipeline
behavior end-to-end (real Playwright fetch of the real local demo fixture, mocked at
the `BrowserCollector` boundary per `tests/core/test_filter_engine_integration.py`'s
own precedent), and that the default (no geo_engine) path is completely unaffected.

Since v2.6 Milestone 2.6.2 (docs/41_Version_2.6_Planning.md), the demo fixture's
listings DO carry real `latitude`/`longitude`. `GeographicEngine.enrich()` therefore
always runs its nearby-places search for them (curated `nearby_amenities` knowledge
entries don't exist for "Example City" either, so those come back as honest
"no curated data yet" placeholders, not fabricated counts) and computes real
distances too, but only once a curated `city_center` reference point also exists for
the search location — nothing seeds that automatically. These tests still prove the
same thing they always did: integration must not crash or degrade the pipeline
regardless of how much geographic evidence exists for a given listing, from "just
coordinates" up to "coordinates plus a curated reference point."
"""

from __future__ import annotations

import contextlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from urllib.request import url2pathname

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.geography import GeographicEngine
from src.geography.history import get_geo_history_for_search
from src.search.search_request import SearchRequest
from src.storage import reference_data_repository
from src.storage.database import Database
from src.storage.models import KnowledgeEntry, Platform
from tests.support import isolated_collectors


class _FileReadingBrowser:
    def fetch(self, url: str, wait_ms: int = 0) -> str:
        return Path(url2pathname(urlparse(url).path)).read_text(encoding="utf-8")


@contextlib.contextmanager
def _mock_browser_collector():
    with patch("src.connectors.sdk.base_connector.BrowserCollector") as mock_cls:
        mock_cls.return_value.__enter__.return_value = _FileReadingBrowser()
        yield


class GeoEngineIntegrationTests(unittest.TestCase):
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

    def test_default_behavior_unchanged_when_no_geo_engine_given(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir)  # no geo_engine
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)  # unaffected by geo engine absence

    def test_geo_engine_runs_without_crashing_when_no_curated_reference_point_exists(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, geo_engine=GeographicEngine())
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)  # geo engine never excludes/crashes the pipeline

    def test_geo_history_confidence_is_none_without_a_curated_reference_point(self) -> None:
        """`GeoHistoryEntry.confidence` is derived only from computed `distances`
        (`src/geography/history.py`) — with real coordinates but no curated
        `city_center` entry for "Example City", `distances` stays empty, so this
        stays honestly `None` even though `nearby` is now populated.
        """
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, geo_engine=GeographicEngine())
        result = agent.run(SearchRequest(location="Example City"))

        with self.db.transaction() as conn:
            history = get_geo_history_for_search(conn, result.search_id)

        self.assertEqual(len(history), 3)  # one row per apartment
        for entry in history:
            self.assertIsNone(entry.confidence)  # honestly no distance evidence, not fabricated

    def test_report_renders_geo_section_with_placeholder_nearby_data(self) -> None:
        """Once apartments have real coordinates, `_render_geo()` renders the geo
        section (its "is there anything to show" check looks at `nearby`, which is
        now always populated — see `src/services/report_generator.py`), but since no
        curated `nearby_amenities`/`city_center` reference data exists for "Example
        City", it honestly shows placeholders, not fabricated counts or distances.
        """
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, geo_engine=GeographicEngine())
        result = agent.run(SearchRequest(location="Example City"))
        html = result.report_path.read_text(encoding="utf-8")
        self.assertIn('class="geo"', html)
        self.assertIn("No curated nearby data yet", html)
        self.assertIn("<li>n/a</li>", html)  # distance summary: still no city_center reference point

    def test_curated_reference_point_produces_real_distances_once_coordinates_exist(self) -> None:
        """Now that the demo fixture's apartments carry real coordinates (v2.6
        Milestone 2.6.2), a curated `city_center` reference point for the search
        location is enough, by itself, to produce real, non-fabricated distances —
        the opposite of this test's pre-2.6.2 behavior (see git history), where the
        same reference point alone did nothing because coordinates didn't exist yet.
        """
        with self.db.transaction() as conn:
            reference_data_repository.upsert_knowledge_entry(
                conn,
                KnowledgeEntry(
                    id=None, category="city_center", key="Example City",
                    value_json=json.dumps({"latitude": 40.0, "longitude": -74.0}),
                    source="manual", updated_at=datetime.now(timezone.utc),
                ),
            )

        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, geo_engine=GeographicEngine())
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)

        with self.db.transaction() as conn:
            history = get_geo_history_for_search(conn, result.search_id)
        self.assertTrue(all(entry.confidence is not None for entry in history))

        html = result.report_path.read_text(encoding="utf-8")
        self.assertIn('class="geo"', html)
        self.assertIn("km", html)  # a real computed distance, not the "n/a" placeholder
        self.assertNotIn("<li>n/a</li>", html)


if __name__ == "__main__":
    unittest.main()
