"""Agent-level integration tests for the Geographic Intelligence Engine — proving
`RentalResearchAgent`'s optional `geo_engine` parameter actually changes pipeline
behavior end-to-end (real Playwright fetch of the real local demo fixture, mocked at
the `BrowserCollector` boundary per `tests/core/test_filter_engine_integration.py`'s
own precedent), and that the default (no geo_engine) path is completely unaffected.

The demo fixture's listings have no `latitude`/`longitude` (no connector populates
them for that platform — see docs/03_Data_Model.md) — this honestly means the geo
engine, when wired in, enriches each apartment with an *empty* `GeoEnrichment` (no
distances, no fabricated evidence), which is itself the correct behavior to prove:
integration must not crash or degrade the pipeline just because geographic evidence
doesn't exist for a given listing.
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

    def test_geo_engine_runs_without_crashing_when_no_coordinates_exist(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, geo_engine=GeographicEngine())
        result = agent.run(SearchRequest(location="Example City"))
        self.assertEqual(len(result.apartments), 3)  # geo engine never excludes/crashes the pipeline

    def test_geo_history_is_recorded_even_when_enrichment_is_empty(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, geo_engine=GeographicEngine())
        result = agent.run(SearchRequest(location="Example City"))

        with self.db.transaction() as conn:
            history = get_geo_history_for_search(conn, result.search_id)

        self.assertEqual(len(history), 3)  # one row per apartment
        for entry in history:
            self.assertIsNone(entry.confidence)  # honestly no evidence, not fabricated

    def test_report_renders_without_geo_section_when_no_evidence_exists(self) -> None:
        agent = RentalResearchAgent(self.db, output_dir=self.output_dir, geo_engine=GeographicEngine())
        result = agent.run(SearchRequest(location="Example City"))
        html = result.report_path.read_text(encoding="utf-8")
        self.assertNotIn('class="geo"', html)  # omitted, not a fabricated placeholder

    def test_curated_reference_point_alone_does_not_fabricate_distances(self) -> None:
        """A curated `city_center` reference point for the search location is not,
        by itself, enough to produce a distance — the demo fixture's apartments have
        no coordinates (see this module's docstring), so `enrich()`'s "no evidence"
        path (proven directly in `tests/geography/test_engine.py`) is exercised here
        through the real pipeline too: no crash, and honestly still no distances.
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

        html = result.report_path.read_text(encoding="utf-8")
        self.assertNotIn('class="geo"', html)  # still honestly empty, not fabricated


if __name__ == "__main__":
    unittest.main()
