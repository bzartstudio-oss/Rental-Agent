"""Phase 2 exit-criteria test (docs/10_Roadmap.md): DiscoveryAgent.discover(request)
returns a registered seed platform.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.discovery.discovery_agent import DiscoveryAgent
from src.storage.database import Database
from src.storage.models import Platform


class DiscoveryAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.agent = DiscoveryAgent(self.db)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _register(self, id_: str, is_active: bool) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id=id_,
                    name=id_,
                    base_url="https://example.com",
                    connector_module=f"src.connectors.{id_}",
                    is_active=is_active,
                    created_at=datetime.now(timezone.utc),
                ),
            )

    def test_discover_returns_the_seed_platform(self) -> None:
        self._register("seed_platform", is_active=True)

        results = self.agent.discover(request=None)

        self.assertEqual([p.id for p in results], ["seed_platform"])

    def test_discover_excludes_inactive_platforms(self) -> None:
        self._register("active_platform", is_active=True)
        self._register("retired_platform", is_active=False)

        results = self.agent.discover(request=None)

        self.assertEqual([p.id for p in results], ["active_platform"])

    def test_discover_returns_empty_list_when_no_platforms_registered(self) -> None:
        results = self.agent.discover(request=None)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
