"""`create_app()` startup-sequence tests — v2.7 Milestone 2.7.1. See
docs/46_Version_2.7_Planning.md Finding 1: the production web app never
called `DiscoveryAgent.sync_platforms()` the way `ui/cli.py` already does on
every startup, so a deployment that only ever runs the web server (never the
CLI) showed zero connector-available platforms and RentCast — fully built,
never reachable — could never actually be queried. These tests prove the
fix directly against a fresh database `create_app()` has never seen before,
deliberately not using `tests/web/helpers.py::web_test_app()` (which
pre-registers `demo_platform` itself) so the registration observed here is
provably `create_app()`'s own doing.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.discovery import platform_registry
from src.storage.database import Database
from src.web.application import create_app
from src.web.configuration import WebConfiguration
from tests.support import isolated_collectors


def _fresh_app_and_db(tmp_path: Path) -> tuple[Database, "Flask"]:  # noqa: F821 - Flask imported lazily below
    db = Database(db_path=tmp_path / "test.db")
    configuration = WebConfiguration(
        host="127.0.0.1", port=0, secret_key="test-secret",
        data_dir=tmp_path, output_dir=tmp_path / "output",
    )
    app = create_app(db=db, configuration=configuration)
    return db, app


class PlatformRegistryActivationTests(unittest.TestCase):
    """Regression coverage for Milestone 2.7.1."""

    def test_create_app_registers_platforms_on_a_fresh_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with isolated_collectors(tmp_path):
                db, _app = _fresh_app_and_db(tmp_path)

                with db.transaction() as conn:
                    available = platform_registry.list_connector_available_platforms(conn)

                available_ids = {p.id for p in available}
                self.assertIn("demo_platform", available_ids)
                self.assertIn("demo_platform_two", available_ids)
                self.assertIn("rentcast", available_ids)

    def test_rentcast_is_registered_and_connector_available_after_init(self) -> None:
        """Verifies the exact production symptom this milestone fixes: RentCast
        must appear as connector-available immediately after `create_app()`
        returns, with no prior CLI run and no API key configured.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with isolated_collectors(tmp_path):
                with patch.dict("os.environ", {}, clear=False):
                    import os

                    os.environ.pop("RENTCAST_API_KEY", None)
                    db, _app = _fresh_app_and_db(tmp_path)

                with db.transaction() as conn:
                    rentcast = platform_registry.get_platform(conn, "rentcast")

                self.assertIsNotNone(rentcast)
                self.assertTrue(rentcast.connector_available)
                self.assertEqual(rentcast.connector_name, "rentcast")

    def test_startup_succeeds_with_no_optional_connectors_configured(self) -> None:
        """No RENTCAST_API_KEY, no SMTP/webhook env vars — the exact zero-config
        state a brand-new production deployment starts in. `create_app()` must
        not raise, and the app it returns must be usable.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with isolated_collectors(tmp_path):
                with patch.dict("os.environ", {}, clear=False):
                    import os

                    for key in ("RENTCAST_API_KEY", "SMTP_HOST", "WEBHOOK_URL"):
                        os.environ.pop(key, None)
                    db, app = _fresh_app_and_db(tmp_path)

                app.config["TESTING"] = True
                client = app.test_client()
                response = client.get("/api/v1/health")
                self.assertEqual(response.status_code, 200)

    def test_sync_on_startup_is_idempotent_across_repeated_calls(self) -> None:
        """Simulates a second worker process (or a restart) calling `create_app()`
        again against the same on-disk database — must not duplicate rows or
        raise, and existing metadata must remain exactly one row per platform.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with isolated_collectors(tmp_path):
                configuration = WebConfiguration(
                    host="127.0.0.1", port=0, secret_key="test-secret",
                    data_dir=tmp_path, output_dir=tmp_path / "output",
                )
                db = Database(db_path=tmp_path / "test.db")

                create_app(db=db, configuration=configuration)
                create_app(db=db, configuration=configuration)
                create_app(db=db, configuration=configuration)

                with db.transaction() as conn:
                    all_platforms = platform_registry.list_all_platforms(conn)

                rentcast_rows = [p for p in all_platforms if p.id == "rentcast"]
                self.assertEqual(len(rentcast_rows), 1)

    def test_cli_startup_behavior_is_unchanged(self) -> None:
        """Preserves existing CLI behavior (Task 4): `ui/cli.py` must still make
        its own `sync_platforms()` call independently of the web app — this
        milestone adds a second caller, it does not remove or alter the first.
        """
        from src.discovery.known_platforms import ALL_KNOWN_PLATFORMS
        from src.ui import cli as ui_cli

        source = Path(ui_cli.__file__).read_text(encoding="utf-8")
        self.assertIn("DiscoveryAgent(db).sync_platforms(ALL_KNOWN_PLATFORMS)", source)
        self.assertTrue(len(ALL_KNOWN_PLATFORMS) >= 3)


if __name__ == "__main__":
    unittest.main()
