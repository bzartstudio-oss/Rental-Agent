import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.analyzers import engine
from src.connectors.base import RawListing
from src.storage import apartment_repository
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
                "INSERT INTO platforms (id, name, base_url, connector_module, is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test_platform", "Test", "https://example.com", "src.connectors.test", 1,
                 datetime.now(timezone.utc).isoformat()),
            )

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def _raw(self, listing_id="listing-1", price=1000.0, status="available", images=None) -> RawListing:
        return RawListing(
            platform_listing_id=listing_id,
            title="Test Listing",
            price=price,
            url="https://example.com/listing-1",
            bedrooms=2.0,
            bathrooms=1.0,
            sqft=800.0,
            address_raw="123 Test St",
            status=status,
            image_urls=images or [],
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


if __name__ == "__main__":
    unittest.main()
