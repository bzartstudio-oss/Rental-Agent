import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.storage.database import Database
from src.storage.models import Platform


class PlatformRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _make_platform(self, id_: str = "seed_platform", is_active: bool = True) -> Platform:
        return Platform(
            id=id_,
            name="Seed Platform",
            base_url="https://example.com",
            connector_module="src.connectors.seed_platform",
            is_active=is_active,
            created_at=datetime.now(timezone.utc),
        )

    def test_register_and_get_platform(self) -> None:
        platform = self._make_platform()
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, platform)

        with self.db.transaction() as conn:
            fetched = platform_registry.get_platform(conn, "seed_platform")

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Seed Platform")
        self.assertEqual(fetched.connector_module, "src.connectors.seed_platform")
        self.assertTrue(fetched.is_active)

    def test_get_platform_returns_none_when_not_registered(self) -> None:
        with self.db.transaction() as conn:
            fetched = platform_registry.get_platform(conn, "does_not_exist")
        self.assertIsNone(fetched)

    def test_list_active_platforms_excludes_inactive(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, self._make_platform("active_one", is_active=True))
            platform_registry.register_platform(conn, self._make_platform("inactive_one", is_active=False))

        with self.db.transaction() as conn:
            active = platform_registry.list_active_platforms(conn)

        self.assertEqual([p.id for p in active], ["active_one"])

    def test_set_platform_active_toggles_without_deleting(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, self._make_platform("toggle_me", is_active=True))
            platform_registry.set_platform_active(conn, "toggle_me", False)

        with self.db.transaction() as conn:
            active = platform_registry.list_active_platforms(conn)
            still_there = platform_registry.get_platform(conn, "toggle_me")

        self.assertEqual(active, [])
        self.assertIsNotNone(still_there)  # retired, not deleted — Principle 1
        self.assertFalse(still_there.is_active)

    def test_registering_duplicate_id_raises(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, self._make_platform("dup"))

        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as conn:
                platform_registry.register_platform(conn, self._make_platform("dup"))


if __name__ == "__main__":
    unittest.main()
