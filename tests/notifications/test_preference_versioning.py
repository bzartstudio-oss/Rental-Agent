"""`NotificationEngine.create_preference()`/`update_preference()`/
`set_enabled()` — "Never overwrite preferences. Every change creates a new
immutable NotificationPreferenceVersion" (the mission's own words).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.notifications import NotificationEngine, service
from src.notifications.exceptions import NotificationValidationError
from src.storage.database import Database
from tests.notifications import helpers


class PreferenceVersioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.engine = NotificationEngine()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_create_preference_requires_a_profile_id(self) -> None:
        with self.assertRaises(NotificationValidationError):
            self.engine.create_preference(self.db, "", enabled_channels=["console"])

    def test_create_preference_requires_at_least_one_channel(self) -> None:
        with self.assertRaises(NotificationValidationError):
            self.engine.create_preference(self.db, "profile-1", enabled_channels=[])

    def test_create_preference_writes_version_one(self) -> None:
        preference = self.engine.create_preference(self.db, "profile-1", enabled_channels=["console"])
        with self.db.transaction() as conn:
            stored = service.get_preference(conn, preference.preference_id)
            version = service.get_latest_preference_version(conn, preference.preference_id)
        self.assertEqual(stored.current_version, 1)
        self.assertEqual(version.version, 1)
        self.assertTrue(stored.enabled)

    def test_update_creates_a_new_version_without_touching_the_old_one(self) -> None:
        preference = self.engine.create_preference(self.db, "profile-1", enabled_channels=["console"])
        self.engine.update_preference(self.db, preference.preference_id, enabled_channels=["console", "file"])

        with self.db.transaction() as conn:
            stored = service.get_preference(conn, preference.preference_id)
            v1 = service.get_preference_version(conn, preference.preference_id, 1)
            v2 = service.get_preference_version(conn, preference.preference_id, 2)

        self.assertEqual(stored.current_version, 2)
        self.assertEqual(v1.enabled_channels, ["console"])  # prior version untouched — still reproducible
        self.assertEqual(v2.enabled_channels, ["console", "file"])

    def test_update_preserves_fields_not_explicitly_overridden(self) -> None:
        preference = self.engine.create_preference(self.db, "profile-1", enabled_channels=["console"], minimum_significance=0.4)
        self.engine.update_preference(self.db, preference.preference_id, enabled_channels=["file"])

        with self.db.transaction() as conn:
            v2 = service.get_latest_preference_version(conn, preference.preference_id)
        self.assertEqual(v2.minimum_significance, 0.4)  # carried forward, not reset

    def test_update_unknown_preference_raises(self) -> None:
        with self.assertRaises(NotificationValidationError):
            self.engine.update_preference(self.db, "does-not-exist", enabled_channels=["console"])

    def test_enable_disable_round_trip(self) -> None:
        preference = self.engine.create_preference(self.db, "profile-1", enabled_channels=["console"])
        self.engine.set_enabled(self.db, preference.preference_id, False)
        with self.db.transaction() as conn:
            self.assertFalse(service.get_preference(conn, preference.preference_id).enabled)

        self.engine.set_enabled(self.db, preference.preference_id, True)
        with self.db.transaction() as conn:
            self.assertTrue(service.get_preference(conn, preference.preference_id).enabled)

    def test_saved_search_scoped_preference_stores_the_saved_search_id(self) -> None:
        saved_search = helpers.make_saved_search(self.db)
        preference = self.engine.create_preference(self.db, "profile-1", saved_search_id=saved_search.saved_search_id, enabled_channels=["console"])
        self.assertEqual(preference.saved_search_id, saved_search.saved_search_id)


if __name__ == "__main__":
    unittest.main()
