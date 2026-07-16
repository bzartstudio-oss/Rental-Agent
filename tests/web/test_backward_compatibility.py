"""Backward-compatibility tests — see docs/32_Web_Dashboard.md "Architecture":
"The CLI must continue working unchanged." Runs the real `ui.cli` entry point
against the same database shape the web layer uses, proving the web package's
existence (and its one additive change to `core/agent.py`'s `SearchRunResult`)
never altered CLI behavior.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.discovery import platform_registry
from src.storage.database import Database
from src.storage.models import Platform
from src.ui import cli as ui_cli
from tests.support import isolated_collectors


class CliBackwardCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.db = Database(db_path=self.tmp_path / "test.db")
        with self.db.transaction() as conn:
            from datetime import datetime, timezone
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform", name="Demo Platform", country="N/A (local fixture)", homepage="local-fixture",
                    connector_available=True, connector_name="demo_platform", created_at=datetime.now(timezone.utc),
                ),
            )
        self._collectors_cm = isolated_collectors(self.tmp_path)
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_cli_main_still_runs_a_search_end_to_end(self) -> None:
        exit_code = ui_cli.main(["--location", "Example City"], db=self.db, output_dir=self.tmp_path / "output")
        self.assertEqual(exit_code, 0)

    def test_cli_main_still_supports_ranking_v2_flag(self) -> None:
        exit_code = ui_cli.main(
            ["--location", "Example City", "--use-ranking-v2"], db=self.db, output_dir=self.tmp_path / "output"
        )
        self.assertEqual(exit_code, 0)

    def test_search_run_result_ranking_v2_field_defaults_to_none(self) -> None:
        """The one field added to `SearchRunResult` for the web layer
        (`ranking_v2_results`) must be optional and default to `None` — every
        caller that doesn't pass `ranking_engine_v2` (which is every existing
        CLI/test call site) must see byte-identical behavior.
        """
        from src.core.agent import RentalResearchAgent
        from src.search.search_request import SearchRequest

        agent = RentalResearchAgent(self.db, output_dir=self.tmp_path / "output")
        result = agent.run(SearchRequest(location="Example City"))
        self.assertIsNone(result.ranking_v2_results)


if __name__ == "__main__":
    unittest.main()
