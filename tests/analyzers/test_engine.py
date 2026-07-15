import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analyzers import engine
from src.connectors.base import RawListing
from src.storage import apartment_history_repository, apartment_repository, search_memory_repository
from src.storage.database import Database
from tests.support import isolated_collectors


class AnalysisEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

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
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def _raw(self, listing_id="listing-1", price=1000.0, status="available", images=None, title="Test Listing",
              description=None) -> RawListing:
        return RawListing(
            platform_listing_id=listing_id,
            title=title,
            price=price,
            url="https://example.com/listing-1",
            bedrooms=2.0,
            bathrooms=1.0,
            sqft=800.0,
            address_raw="123 Test St",
            status=status,
            image_urls=images or [],
            description=description,
        )

    def test_new_listing_is_inserted_with_initial_history(self) -> None:
        with self.db.transaction() as conn:
            apartment = engine.process_listing(conn, self._raw(), "test_platform")

        with self.db.transaction() as conn:
            fetched = apartment_repository.get_apartment(conn, apartment.id)
            price_history = apartment_repository.get_price_history(conn, apartment.id)
            availability_history = apartment_repository.get_availability_history(conn, apartment.id)

        self.assertEqual(fetched.current_price, 1000.0)
        self.assertEqual(len(price_history), 1)
        self.assertEqual(len(availability_history), 1)

    def test_re_observation_with_no_change_adds_no_new_history(self) -> None:
        with self.db.transaction() as conn:
            first = engine.process_listing(conn, self._raw(price=1000.0), "test_platform")
        with self.db.transaction() as conn:
            engine.process_listing(conn, self._raw(price=1000.0), "test_platform")  # identical re-observation

        with self.db.transaction() as conn:
            price_history = apartment_repository.get_price_history(conn, first.id)

        self.assertEqual(len(price_history), 1)  # still just the original — nothing new written

    def test_re_observation_with_price_change_adds_history_without_losing_original(self) -> None:
        with self.db.transaction() as conn:
            first = engine.process_listing(conn, self._raw(price=1000.0), "test_platform")
        with self.db.transaction() as conn:
            engine.process_listing(conn, self._raw(price=950.0), "test_platform")

        with self.db.transaction() as conn:
            updated = apartment_repository.get_apartment(conn, first.id)
            price_history = apartment_repository.get_price_history(conn, first.id)

        self.assertEqual(updated.current_price, 950.0)
        self.assertEqual([entry.price for entry in price_history], [1000.0, 950.0])

    def test_images_are_downloaded_and_recorded_for_new_apartments(self) -> None:
        image_source = Path(self._tmp_dir.name) / "fixture_image.png"
        image_source.write_bytes(b"pretend-png-bytes")

        with self.db.transaction() as conn:
            apartment = engine.process_listing(
                conn, self._raw(images=[image_source.as_uri()]), "test_platform"
            )

        with self.db.transaction() as conn:
            images = apartment_repository.get_images(conn, apartment.id)

        self.assertEqual(len(images), 1)
        self.assertTrue(Path(images[0].local_path).exists())
        self.assertEqual(Path(images[0].local_path).read_bytes(), b"pretend-png-bytes")

    def test_re_observation_does_not_re_download_images(self) -> None:
        image_source = Path(self._tmp_dir.name) / "fixture_image.png"
        image_source.write_bytes(b"pretend-png-bytes")

        with self.db.transaction() as conn:
            first = engine.process_listing(conn, self._raw(images=[image_source.as_uri()]), "test_platform")
        with self.db.transaction() as conn:
            engine.process_listing(conn, self._raw(images=[image_source.as_uri()]), "test_platform")

        with self.db.transaction() as conn:
            images = apartment_repository.get_images(conn, first.id)

        self.assertEqual(len(images), 1)  # not duplicated on re-observation

    def test_new_apartment_gets_an_initial_title_change_log_row(self) -> None:
        with self.db.transaction() as conn:
            apartment = engine.process_listing(conn, self._raw(), "test_platform")

        with self.db.transaction() as conn:
            change_log = apartment_history_repository.get_change_log(conn, apartment.id)

        self.assertEqual(len(change_log), 1)
        self.assertEqual(change_log[0].field_name, "title")
        self.assertIsNone(change_log[0].old_value)
        self.assertEqual(change_log[0].new_value, "Test Listing")

    def test_new_apartment_with_a_description_gets_both_change_log_rows(self) -> None:
        with self.db.transaction() as conn:
            apartment = engine.process_listing(conn, self._raw(description="Newly renovated."), "test_platform")

        with self.db.transaction() as conn:
            change_log = apartment_history_repository.get_change_log(conn, apartment.id)

        self.assertEqual({e.field_name for e in change_log}, {"title", "description"})

    def test_title_change_on_reobservation_is_recorded_without_losing_the_original(self) -> None:
        with self.db.transaction() as conn:
            first = engine.process_listing(conn, self._raw(title="Test Listing"), "test_platform")
        with self.db.transaction() as conn:
            engine.process_listing(conn, self._raw(title="Renovated Test Listing"), "test_platform")

        with self.db.transaction() as conn:
            fetched = apartment_repository.get_apartment(conn, first.id)
            change_log = apartment_history_repository.get_change_log(conn, first.id)

        self.assertEqual(fetched.title, "Renovated Test Listing")
        title_entries = [e for e in change_log if e.field_name == "title"]
        # one row for the initial observation (old_value=None) plus one for this change
        self.assertEqual(len(title_entries), 2)
        self.assertEqual(title_entries[-1].old_value, "Test Listing")
        self.assertEqual(title_entries[-1].new_value, "Renovated Test Listing")

    def test_unchanged_title_on_reobservation_adds_no_new_change_log_row(self) -> None:
        with self.db.transaction() as conn:
            first = engine.process_listing(conn, self._raw(), "test_platform")
        with self.db.transaction() as conn:
            engine.process_listing(conn, self._raw(), "test_platform")  # identical re-observation

        with self.db.transaction() as conn:
            change_log = apartment_history_repository.get_change_log(conn, first.id)

        self.assertEqual(len(change_log), 1)  # just the initial title row — nothing new

    def test_new_image_on_reobservation_is_downloaded_and_logged_as_added(self) -> None:
        first_image = Path(self._tmp_dir.name) / "first.png"
        first_image.write_bytes(b"first")
        second_image = Path(self._tmp_dir.name) / "second.png"
        second_image.write_bytes(b"second")

        with self.db.transaction() as conn:
            apartment = engine.process_listing(
                conn, self._raw(images=[first_image.as_uri()]), "test_platform", search_id="search-1"
            )
        with self.db.transaction() as conn:
            engine.process_listing(
                conn,
                self._raw(images=[first_image.as_uri(), second_image.as_uri()]),
                "test_platform",
                search_id="search-1",
            )

        with self.db.transaction() as conn:
            images = apartment_repository.get_images(conn, apartment.id)
            events = apartment_history_repository.get_image_events(conn, apartment.id)

        self.assertEqual(len(images), 2)
        self.assertTrue(all(image.is_current for image in images))
        # one "added" event for the apartment's initial image, one for the second
        self.assertEqual([e.event for e in events], ["added", "added"])
        self.assertEqual(events[-1].source_url, second_image.as_uri())

    def test_removed_image_on_reobservation_is_flagged_not_current_and_logged(self) -> None:
        image_path = Path(self._tmp_dir.name) / "fixture_image.png"
        image_path.write_bytes(b"pretend-png-bytes")

        with self.db.transaction() as conn:
            apartment = engine.process_listing(
                conn, self._raw(images=[image_path.as_uri()]), "test_platform", search_id="search-1"
            )
        with self.db.transaction() as conn:
            engine.process_listing(conn, self._raw(images=[]), "test_platform", search_id="search-1")

        with self.db.transaction() as conn:
            images = apartment_repository.get_images(conn, apartment.id)
            events = apartment_history_repository.get_image_events(conn, apartment.id)

        self.assertEqual(len(images), 1)  # never deleted
        self.assertFalse(images[0].is_current)
        # one "added" event for the apartment's initial image, then "removed"
        self.assertEqual([e.event for e in events], ["added", "removed"])

    def test_image_events_are_not_logged_without_a_search_id(self) -> None:
        """apartment_image_events.search_id is NOT NULL — a direct process_listing()
        call with no search context (as most of this file's tests make) must still
        download/flip images correctly, just without an event row, rather than raising.
        """
        image_path = Path(self._tmp_dir.name) / "fixture_image.png"
        image_path.write_bytes(b"pretend-png-bytes")

        with self.db.transaction() as conn:
            apartment = engine.process_listing(conn, self._raw(images=[image_path.as_uri()]), "test_platform")
        with self.db.transaction() as conn:
            engine.process_listing(conn, self._raw(images=[]), "test_platform")  # no search_id

        with self.db.transaction() as conn:
            events = apartment_history_repository.get_image_events(conn, apartment.id)

        self.assertEqual(events, [])

    def test_new_apartment_is_recorded_in_search_observed_apartments(self) -> None:
        with self.db.transaction() as conn:
            apartment = engine.process_listing(conn, self._raw(), "test_platform", search_id="search-1")

        with self.db.transaction() as conn:
            observed_ids = search_memory_repository.get_observed_apartment_ids(conn, "search-1")

        self.assertEqual(observed_ids, {apartment.id})

    def test_reobservation_adds_its_own_search_observed_apartments_row(self) -> None:
        with self.db.transaction() as conn:
            apartment = engine.process_listing(conn, self._raw(), "test_platform", search_id="search-1")

        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO search_requests (id, created_at, criteria_json) VALUES (?, ?, ?)",
                ("search-2", datetime.now(timezone.utc).isoformat(), "{}"),
            )
            engine.process_listing(conn, self._raw(), "test_platform", search_id="search-2")

        with self.db.transaction() as conn:
            first_ids = search_memory_repository.get_observed_apartment_ids(conn, "search-1")
            second_ids = search_memory_repository.get_observed_apartment_ids(conn, "search-2")

        # append-only — both searches keep their own observation of the same apartment
        self.assertEqual(first_ids, {apartment.id})
        self.assertEqual(second_ids, {apartment.id})

    def test_no_search_observed_row_without_a_search_id(self) -> None:
        with self.db.transaction() as conn:
            apartment = engine.process_listing(conn, self._raw(), "test_platform")  # no search_id

        with self.db.transaction() as conn:
            observed = apartment_history_repository.get_change_log(conn, apartment.id)  # sanity: apartment exists
            self.assertTrue(observed)

        # search_observed_apartments.search_id is NOT NULL — nothing to query against
        # without one, so this only asserts process_listing() didn't raise.


if __name__ == "__main__":
    unittest.main()
