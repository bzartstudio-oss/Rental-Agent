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

    def _make_platform(self, id_: str = "seed_platform", connector_available: bool = True) -> Platform:
        return Platform(
            id=id_,
            name="Seed Platform",
            country="Testland",
            homepage="https://example.com",
            supported_cities=["Example City"],
            rental_types=["apartment"],
            requires_login=False,
            connector_available=connector_available,
            connector_name="seed_platform" if connector_available else None,
            discovery_method="manual_seed",
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
        self.assertEqual(fetched.country, "Testland")
        self.assertEqual(fetched.supported_cities, ["Example City"])
        self.assertEqual(fetched.rental_types, ["apartment"])
        self.assertEqual(fetched.connector_name, "seed_platform")
        self.assertTrue(fetched.connector_available)

    def test_get_platform_returns_none_when_not_registered(self) -> None:
        with self.db.transaction() as conn:
            fetched = platform_registry.get_platform(conn, "does_not_exist")
        self.assertIsNone(fetched)

    def test_list_all_platforms_includes_unsupported_ones(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, self._make_platform("supported", connector_available=True))
            platform_registry.register_platform(conn, self._make_platform("unsupported", connector_available=False))

        with self.db.transaction() as conn:
            all_platforms = platform_registry.list_all_platforms(conn)

        self.assertEqual({p.id for p in all_platforms}, {"supported", "unsupported"})

    def test_list_connector_available_platforms_excludes_unsupported(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, self._make_platform("supported", connector_available=True))
            platform_registry.register_platform(conn, self._make_platform("unsupported", connector_available=False))

        with self.db.transaction() as conn:
            available = platform_registry.list_connector_available_platforms(conn)

        self.assertEqual([p.id for p in available], ["supported"])

    def test_update_platform_metadata_overwrites_fields_but_keeps_identity(self) -> None:
        original = self._make_platform("update_me")
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, original)

        updated = self._make_platform("update_me")
        updated.name = "Renamed Platform"
        updated.supported_cities = ["New City"]
        updated.last_verified = datetime.now(timezone.utc)

        with self.db.transaction() as conn:
            platform_registry.update_platform_metadata(conn, "update_me", updated)

        with self.db.transaction() as conn:
            fetched = platform_registry.get_platform(conn, "update_me")

        self.assertEqual(fetched.id, "update_me")  # identity preserved
        self.assertEqual(fetched.name, "Renamed Platform")
        self.assertEqual(fetched.supported_cities, ["New City"])
        self.assertIsNotNone(fetched.last_verified)

    def test_mark_connector_unavailable_retires_without_deleting(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, self._make_platform("toggle_me", connector_available=True))
            platform_registry.mark_connector_unavailable(conn, "toggle_me", note="Connector removed for testing")

        with self.db.transaction() as conn:
            available = platform_registry.list_connector_available_platforms(conn)
            still_there = platform_registry.get_platform(conn, "toggle_me")

        self.assertEqual(available, [])
        self.assertIsNotNone(still_there)  # retired, not deleted — Principle 1
        self.assertFalse(still_there.connector_available)
        self.assertIsNone(still_there.connector_name)
        self.assertEqual(still_there.notes, "Connector removed for testing")

    def test_mark_connector_unavailable_raises_for_unknown_platform(self) -> None:
        with self.db.transaction() as conn:
            with self.assertRaises(KeyError):
                platform_registry.mark_connector_unavailable(conn, "does_not_exist")

    def test_registering_duplicate_id_raises(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, self._make_platform("dup"))

        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as conn:
                platform_registry.register_platform(conn, self._make_platform("dup"))


if __name__ == "__main__":
    unittest.main()
