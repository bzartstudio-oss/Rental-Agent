"""Tests for src/history/history_service.py — the Apartment History Engine's write
(record_new_apartment/record_reobservation) and read (latest/previous version,
timelines, change_timeline) sides. Uses a real temporary SQLite database, never the
real data/rental_intelligence.db.
"""

import json
import time
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.history import history_service
from src.storage import apartment_history_repository, apartment_repository
from src.storage.database import Database
from src.storage.models import (
    Apartment,
    ApartmentAvailabilityHistoryEntry,
    ApartmentPriceHistoryEntry,
)


class HistoryServiceTestCase(unittest.TestCase):
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

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _make_apartment(self, when: datetime, **overrides) -> Apartment:
        defaults = dict(
            id="apt-1",
            platform_id="test_platform",
            platform_listing_id="listing-1",
            title="Sunny 2BR",
            url="https://example.com/listing-1",
            current_price=1500.0,
            current_status="available",
            first_seen_at=when,
            last_seen_at=when,
        )
        defaults.update(overrides)
        return Apartment(**defaults)


class RecordNewApartmentTests(HistoryServiceTestCase):
    def test_writes_initial_title_change_log_row(self) -> None:
        apartment = self._make_apartment(datetime.now(timezone.utc))

        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)
            changes = history_service.record_new_apartment(conn, apartment, apartment.first_seen_at, "search-1")

        with self.db.transaction() as conn:
            change_log = apartment_history_repository.get_change_log(conn, "apt-1")

        self.assertEqual(len(changes), 1)
        self.assertEqual(change_log[0].field_name, "title")
        self.assertIsNone(change_log[0].old_value)
        self.assertEqual(change_log[0].new_value, "Sunny 2BR")

    def test_writes_description_row_only_when_description_present(self) -> None:
        apartment = self._make_apartment(datetime.now(timezone.utc), description="Newly renovated.")

        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)
            history_service.record_new_apartment(conn, apartment, apartment.first_seen_at, "search-1")

        with self.db.transaction() as conn:
            change_log = apartment_history_repository.get_change_log(conn, "apt-1")

        fields = {entry.field_name for entry in change_log}
        self.assertEqual(fields, {"title", "description"})

    def test_no_description_row_when_description_absent(self) -> None:
        apartment = self._make_apartment(datetime.now(timezone.utc))  # description defaults None

        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)
            history_service.record_new_apartment(conn, apartment, apartment.first_seen_at, "search-1")

        with self.db.transaction() as conn:
            change_log = apartment_history_repository.get_change_log(conn, "apt-1")

        self.assertEqual([entry.field_name for entry in change_log], ["title"])


class RecordReobservationTests(HistoryServiceTestCase):
    def test_no_change_writes_nothing(self) -> None:
        apartment = self._make_apartment(datetime.now(timezone.utc))
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)

        with self.db.transaction() as conn:
            fields = {"title": apartment.title, "description": apartment.description}
            changes = history_service.record_reobservation(conn, apartment, fields, datetime.now(timezone.utc), "search-1")

        self.assertEqual(changes, [])

    def test_title_change_is_recorded_and_summarized(self) -> None:
        apartment = self._make_apartment(datetime.now(timezone.utc))
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)

        with self.db.transaction() as conn:
            fields = {"title": "Renovated Sunny 2BR", "description": None}
            changes = history_service.record_reobservation(conn, apartment, fields, datetime.now(timezone.utc), "search-1")

        with self.db.transaction() as conn:
            change_log = apartment_history_repository.get_change_log(conn, "apt-1")

        # itemized title change + a "listing_updated" summary, but the summary itself
        # is not persisted to apartment_change_log (comparison.summarize_listing_updated).
        self.assertEqual(len(changes), 2)
        self.assertEqual(len(change_log), 1)
        self.assertEqual(change_log[0].field_name, "title")
        self.assertEqual(change_log[0].old_value, "Sunny 2BR")
        self.assertEqual(change_log[0].new_value, "Renovated Sunny 2BR")
        self.assertEqual(json.loads(changes[-1].new_value), ["title"])


class LatestAndPreviousVersionTests(HistoryServiceTestCase):
    def test_latest_version_returns_current_row(self) -> None:
        apartment = self._make_apartment(datetime.now(timezone.utc))
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)

        with self.db.transaction() as conn:
            latest = history_service.latest_version(conn, "apt-1")

        self.assertEqual(latest.title, "Sunny 2BR")

    def test_previous_version_is_none_for_a_single_observation(self) -> None:
        apartment = self._make_apartment(datetime.now(timezone.utc))
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)

        with self.db.transaction() as conn:
            previous = history_service.previous_version(conn, "apt-1")

        self.assertIsNone(previous)

    def test_previous_version_reconstructs_price_and_title_before_the_latest_change(self) -> None:
        first_seen = datetime.now(timezone.utc)
        apartment = self._make_apartment(first_seen)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1500.0, observed_at=first_seen)
            )
            history_service.record_new_apartment(conn, apartment, first_seen, "search-1")

        second_seen = first_seen + timedelta(days=7)
        with self.db.transaction() as conn:
            apartment_repository.update_apartment_state(
                conn, apartment_id="apt-1", current_price=1400.0, current_status="available", last_seen_at=second_seen
            )
            apartment_repository.update_apartment_details(conn, apartment_id="apt-1", title="Renovated Sunny 2BR", description=None)
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1400.0, observed_at=second_seen)
            )
            history_service.record_reobservation(
                conn, apartment, {"title": "Renovated Sunny 2BR", "description": None}, second_seen, "search-1"
            )

        with self.db.transaction() as conn:
            previous = history_service.previous_version(conn, "apt-1")

        self.assertEqual(previous.current_price, 1500.0)
        self.assertEqual(previous.title, "Sunny 2BR")


class TimelineTests(HistoryServiceTestCase):
    def test_price_and_availability_timelines_delegate_to_apartment_repository(self) -> None:
        apartment = self._make_apartment(datetime.now(timezone.utc))
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1500.0, observed_at=apartment.first_seen_at)
            )
            apartment_repository.add_availability_history(
                conn, ApartmentAvailabilityHistoryEntry(apartment_id="apt-1", status="available", observed_at=apartment.first_seen_at)
            )

        with self.db.transaction() as conn:
            prices = history_service.price_timeline(conn, "apt-1")
            availability = history_service.availability_timeline(conn, "apt-1")

        self.assertEqual([p.price for p in prices], [1500.0])
        self.assertEqual([a.status for a in availability], ["available"])

    def test_change_timeline_merges_every_tracked_field_in_time_order(self) -> None:
        first_seen = datetime.now(timezone.utc)
        apartment = self._make_apartment(first_seen)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1500.0, observed_at=first_seen, search_id="search-1")
            )
            apartment_repository.add_availability_history(
                conn, ApartmentAvailabilityHistoryEntry(apartment_id="apt-1", status="available", observed_at=first_seen, search_id="search-1")
            )
            history_service.record_new_apartment(conn, apartment, first_seen, "search-1")
            apartment_history_repository.add_image_event(conn, "apt-1", "added", "a.jpg", "search-1", first_seen)

        second_seen = first_seen + timedelta(days=1)
        with self.db.transaction() as conn:
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1400.0, observed_at=second_seen, search_id="search-1")
            )

        with self.db.transaction() as conn:
            timeline = history_service.change_timeline(conn, "apt-1")

        self.assertEqual(len(timeline), 5)  # price(initial) + price(second) + status(initial) + title + image_added
        observed_ats = [change.observed_at for change in timeline]
        self.assertEqual(observed_ats, sorted(observed_ats))


class PerformanceTests(HistoryServiceTestCase):
    def test_change_timeline_stays_fast_with_a_long_history(self) -> None:
        """Regression guard against an obvious N+1 pathology: reconstructing the
        timeline for an apartment with a few hundred recorded changes should still be
        near-instant, not scale badly with history length.
        """
        first_seen = datetime.now(timezone.utc)
        apartment = self._make_apartment(first_seen)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, apartment)

        with self.db.transaction() as conn:
            for i in range(500):
                apartment_history_repository.add_change_log_entry(
                    conn, "apt-1", "description", f"v{i}", f"v{i + 1}", first_seen + timedelta(seconds=i), "search-1"
                )

        started = time.perf_counter()
        with self.db.transaction() as conn:
            timeline = history_service.change_timeline(conn, "apt-1")
        elapsed = time.perf_counter() - started

        self.assertEqual(len(timeline), 500)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
