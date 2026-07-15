"""Round-trip tests for storage/apartment_history_repository.py — the v2.0 Step 2 data
access layer for `apartment_change_log` and `apartment_image_events`.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.storage import apartment_history_repository, apartment_repository
from src.storage.database import Database
from src.storage.models import Apartment


class ApartmentHistoryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO platforms (id, name, country, supported_cities, rental_types, homepage, "
                "connector_available, connector_name, discovery_method, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("test_platform", "Test", "Testland", "[]", "[]", "https://example.com", 1,
                 "src.connectors.test", "manual", datetime.now(timezone.utc).isoformat()),
            )
            conn.execute(
                "INSERT INTO search_requests (id, created_at, criteria_json) VALUES (?, ?, ?)",
                ("search-1", datetime.now(timezone.utc).isoformat(), "{}"),
            )
            apartment_repository.insert_apartment(
                conn,
                Apartment(
                    id="apt-1",
                    platform_id="test_platform",
                    platform_listing_id="listing-1",
                    title="Sunny 2BR",
                    url="https://example.com/listing-1",
                    current_price=1500.0,
                    current_status="available",
                    first_seen_at=datetime.now(timezone.utc),
                    last_seen_at=datetime.now(timezone.utc),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_change_log_round_trip_in_observed_order(self) -> None:
        first = datetime.now(timezone.utc)
        second = first + timedelta(minutes=1)

        with self.db.transaction() as conn:
            apartment_history_repository.add_change_log_entry(
                conn, "apt-1", "title", None, "Sunny 2BR", first, "search-1"
            )
            apartment_history_repository.add_change_log_entry(
                conn, "apt-1", "description", None, "Newly renovated.", second, "search-1"
            )

        with self.db.transaction() as conn:
            entries = apartment_history_repository.get_change_log(conn, "apt-1")

        self.assertEqual([e.field_name for e in entries], ["title", "description"])
        self.assertEqual(entries[1].new_value, "Newly renovated.")
        self.assertEqual(entries[0].search_id, "search-1")

    def test_change_log_entry_allows_a_null_search_id(self) -> None:
        with self.db.transaction() as conn:
            apartment_history_repository.add_change_log_entry(
                conn, "apt-1", "title", "Old", "New", datetime.now(timezone.utc), search_id=None
            )

        with self.db.transaction() as conn:
            entries = apartment_history_repository.get_change_log(conn, "apt-1")

        self.assertIsNone(entries[0].search_id)

    def test_image_event_round_trip_in_observed_order(self) -> None:
        first = datetime.now(timezone.utc)
        second = first + timedelta(minutes=1)

        with self.db.transaction() as conn:
            apartment_history_repository.add_image_event(conn, "apt-1", "added", "a.jpg", "search-1", first)
            apartment_history_repository.add_image_event(conn, "apt-1", "removed", "a.jpg", "search-1", second)

        with self.db.transaction() as conn:
            events = apartment_history_repository.get_image_events(conn, "apt-1")

        self.assertEqual([e.event for e in events], ["added", "removed"])
        self.assertEqual(events[0].source_url, "a.jpg")

    def test_image_event_requires_a_search_id(self) -> None:
        import sqlite3

        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as conn:
                apartment_history_repository.add_image_event(
                    conn, "apt-1", "added", "a.jpg", None, datetime.now(timezone.utc)
                )


class ApartmentRepositoryV2AdditionsTests(unittest.TestCase):
    """update_apartment_details / mark_image_not_current — the two v2.0 Step 2
    additions to storage/apartment_repository.py.
    """

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO platforms (id, name, country, supported_cities, rental_types, homepage, "
                "connector_available, connector_name, discovery_method, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("test_platform", "Test", "Testland", "[]", "[]", "https://example.com", 1,
                 "src.connectors.test", "manual", datetime.now(timezone.utc).isoformat()),
            )
            apartment_repository.insert_apartment(
                conn,
                Apartment(
                    id="apt-1",
                    platform_id="test_platform",
                    platform_listing_id="listing-1",
                    title="Sunny 2BR",
                    url="https://example.com/listing-1",
                    current_price=1500.0,
                    current_status="available",
                    first_seen_at=datetime.now(timezone.utc),
                    last_seen_at=datetime.now(timezone.utc),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_update_apartment_details_updates_title_and_description(self) -> None:
        with self.db.transaction() as conn:
            apartment_repository.update_apartment_details(
                conn, "apt-1", title="Renovated Sunny 2BR", description="Now with a balcony."
            )

        with self.db.transaction() as conn:
            fetched = apartment_repository.get_apartment(conn, "apt-1")

        self.assertEqual(fetched.title, "Renovated Sunny 2BR")
        self.assertEqual(fetched.description, "Now with a balcony.")

    def test_mark_image_not_current_flips_the_flag_without_deleting(self) -> None:
        from src.storage.models import ApartmentImage

        with self.db.transaction() as conn:
            image_id = apartment_repository.add_image(
                conn,
                ApartmentImage(
                    apartment_id="apt-1",
                    source_url="a.jpg",
                    local_path="data/media/apt-1/a.jpg",
                    downloaded_at=datetime.now(timezone.utc),
                ),
            )

        with self.db.transaction() as conn:
            apartment_repository.mark_image_not_current(conn, image_id)

        with self.db.transaction() as conn:
            images = apartment_repository.get_images(conn, "apt-1")

        self.assertEqual(len(images), 1)  # still there — never deleted
        self.assertFalse(images[0].is_current)


if __name__ == "__main__":
    unittest.main()
