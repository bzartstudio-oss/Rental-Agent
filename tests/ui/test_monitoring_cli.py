"""CLI tests for `src/ui/monitoring_cli.py` — mirrors
`tests/ui/test_discovery_cli.py`'s own "drive `main()` against a real temp
database, assert on stdout" shape.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.monitoring import service as monitoring_service
from src.storage.database import Database
from src.storage.models import Platform
from src.ui import monitoring_cli
from tests.support import isolated_collectors

_NOW = datetime.now(timezone.utc)


class MonitoringCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, Platform(
                id="demo_platform", name="Demo Platform", country="N/A (local fixture)", homepage="local-fixture",
                connector_available=True, connector_name="demo_platform", created_at=_NOW,
            ))

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def _run(self, argv: list[str]) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = monitoring_cli.main(argv, db=self.db)
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()

    def test_create_and_list_saved_searches(self) -> None:
        output = self._run(["create-saved-search", "--name", "Example City", "--location", "Example City"])
        self.assertIn("Created saved search", output)

        listing = self._run(["list-saved-searches"])
        self.assertIn("Example City", listing)

    def test_run_now_and_list_events(self) -> None:
        self._run(["create-saved-search", "--name", "Example City", "--location", "Example City"])
        with self.db.transaction() as conn:
            saved_search_id = monitoring_service.get_all_saved_searches(conn)[0].saved_search_id

        run_output = self._run(["run-now", "--saved-search-id", saved_search_id])
        self.assertIn("status=completed", run_output)

        events_output = self._run(["list-events", "--saved-search-id", saved_search_id])
        self.assertIn("monitoring_run_completed", events_output)

    def test_update_saved_search_creates_new_version(self) -> None:
        self._run(["create-saved-search", "--name", "Example City", "--location", "Example City"])
        with self.db.transaction() as conn:
            saved_search_id = monitoring_service.get_all_saved_searches(conn)[0].saved_search_id

        output = self._run(["update-saved-search", "--saved-search-id", saved_search_id, "--location", "Other City"])
        self.assertIn("Created version 2", output)

        view = self._run(["view-saved-search", "--saved-search-id", saved_search_id])
        self.assertIn("Other City", view)

    def test_enable_disable(self) -> None:
        self._run(["create-saved-search", "--name", "Example City", "--location", "Example City"])
        with self.db.transaction() as conn:
            saved_search_id = monitoring_service.get_all_saved_searches(conn)[0].saved_search_id

        self.assertIn("Disabled", self._run(["disable-saved-search", "--saved-search-id", saved_search_id]))
        self.assertIn("Enabled", self._run(["enable-saved-search", "--saved-search-id", saved_search_id]))

    def test_health_and_next_run(self) -> None:
        self._run(["create-saved-search", "--name", "Example City", "--location", "Example City"])
        with self.db.transaction() as conn:
            saved_search_id = monitoring_service.get_all_saved_searches(conn)[0].saved_search_id

        health_output = self._run(["health", "--saved-search-id", saved_search_id])
        self.assertIn("is_healthy=True", health_output)

        next_run_output = self._run(["next-run", "--saved-search-id", saved_search_id])
        self.assertIn("manual only", next_run_output)


if __name__ == "__main__":
    unittest.main()
