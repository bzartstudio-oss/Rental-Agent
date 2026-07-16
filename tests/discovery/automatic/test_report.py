"""Tests for `discovery.automatic.report` — HTML + JSON discovery report
generation from already-stored data.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery.automatic import report, service
from src.discovery.automatic.models import (
    DiscoveryRequest,
    DiscoveryRun,
    PlatformCandidate,
    PlatformClassification,
    PlatformDiscoveryResult,
    PlatformStatus,
)
from src.storage.database import Database

_NOW = datetime.now(timezone.utc)


class GenerateReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self._output_dir = Path(self._tmp_dir.name) / "output"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _seed(self) -> PlatformDiscoveryResult:
        run = DiscoveryRun(
            request=DiscoveryRequest(country="Spain", city="Valencia"), started_at=_NOW, completed_at=_NOW,
            providers_used=["curated_seed"], run_id="r1", total_candidates=1, supported_count=1,
        )
        candidate = PlatformCandidate(
            candidate_id="c1", normalized_domain="example.com", name="Example", raw_url="https://example.com",
            status=PlatformStatus.CONNECTOR_AVAILABLE, classification=PlatformClassification.RENTAL_MARKETPLACE,
            first_discovered_at=_NOW, last_seen_at=_NOW, last_run_id="r1", confidence=0.9, city="Valencia",
        )
        with self.db.transaction() as conn:
            service.record_run(conn, run)
            service.record_candidate(conn, candidate)
        return PlatformDiscoveryResult(run=run, supported=[candidate])

    def test_json_report_has_expected_top_level_shape(self) -> None:
        result = self._seed()
        with self.db.transaction() as conn:
            json_path, html_path = report.generate_report(conn, result, output_dir=self._output_dir)

        self.assertTrue(json_path.exists())
        self.assertTrue(html_path.exists())
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["run_id"], "r1")
        self.assertEqual(data["request"]["country"], "Spain")
        self.assertEqual(len(data["supported_platforms"]), 1)
        self.assertEqual(data["supported_platforms"][0]["original_url"], "https://example.com")
        self.assertIn("Valencia", data["geographic_coverage"])

    def test_html_report_contains_candidate_name_and_original_url(self) -> None:
        result = self._seed()
        with self.db.transaction() as conn:
            _json_path, html_path = report.generate_report(conn, result, output_dir=self._output_dir)

        html = html_path.read_text(encoding="utf-8")
        self.assertIn("Example", html)
        self.assertIn("https://example.com", html)
        self.assertIn("Supported Platforms", html)


if __name__ == "__main__":
    unittest.main()
