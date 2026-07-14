"""Phase 1 exit-criteria test (docs/10_Roadmap.md): a hand-crafted Apartment and its
history must round-trip through insert/read, and re-observing an apartment with a changed
price must add a new history row rather than lose the old one — proving Principles 1 and 3
from docs/00_Project_Vision.md (never lose information; historical versions) actually hold,
not just that the schema exists in theory.

Uses a temporary SQLite file per test (never the real data/rental_intelligence.db), so this
test is isolated and safe to run repeatedly.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.storage import apartment_repository as apartments
from src.storage.database import Database
from src.storage.models import (
    Apartment,
    ApartmentAvailabilityHistoryEntry,
    ApartmentImage,
    ApartmentPriceHistoryEntry,
)


class ApartmentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp_dir.name) / "test.db"
        self.db = Database(db_path=db_path)

        # storage/ doesn't own platform registration (that's discovery/platform_registry.py,
        # Phase 2) — inserting the row directly here keeps this test scoped to storage only.
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO platforms (id, name, base_url, connector_module, is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "test_platform",
                    "Test Platform",
                    "https://example.com",
                    "src.connectors.test_platform",
                    1,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _make_apartment(self, when: datetime) -> Apartment:
        return Apartment(
            id="apt-1",
            platform_id="test_platform",
            platform_listing_id="listing-123",
            title="Sunny 2BR near downtown",
            url="https://example.com/listing-123",
            current_price=1500.0,
            current_status="available",
            first_seen_at=when,
            last_seen_at=when,
            bedrooms=2,
            bathrooms=1,
            sqft=850,
        )

    def test_apartment_and_history_round_trip(self) -> None:
        first_seen = datetime.now(timezone.utc)
        apartment = self._make_apartment(first_seen)

        with self.db.transaction() as conn:
            apartments.insert_apartment(conn, apartment)
            apartments.add_price_history(
                conn,
                ApartmentPriceHistoryEntry(apartment_id=apartment.id, price=1500.0, observed_at=first_seen),
            )
            apartments.add_availability_history(
                conn,
                ApartmentAvailabilityHistoryEntry(
                    apartment_id=apartment.id, status="available", observed_at=first_seen
                ),
            )
            apartments.add_image(
                conn,
                ApartmentImage(
                    apartment_id=apartment.id,
                    source_url="https://example.com/photo1.jpg",
                    local_path="data/media/apt-1/photo1.jpg",
                    downloaded_at=first_seen,
                ),
            )

        with self.db.transaction() as conn:
            fetched = apartments.get_apartment(conn, "apt-1")
            fetched_by_listing = apartments.get_apartment_by_platform_listing(
                conn, "test_platform", "listing-123"
            )
            price_history = apartments.get_price_history(conn, "apt-1")
            availability_history = apartments.get_availability_history(conn, "apt-1")
            images = apartments.get_images(conn, "apt-1")

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, apartment.title)
        self.assertEqual(fetched.current_price, 1500.0)
        self.assertEqual(fetched.bedrooms, 2)
        self.assertEqual(fetched_by_listing.id, "apt-1")

        self.assertEqual(len(price_history), 1)
        self.assertEqual(price_history[0].price, 1500.0)

        self.assertEqual(len(availability_history), 1)
        self.assertEqual(availability_history[0].status, "available")

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].source_url, "https://example.com/photo1.jpg")

    def test_re_observation_adds_history_without_losing_the_original(self) -> None:
        """Principles 1 & 3 (docs/00_Project_Vision.md): re-observing an apartment with a
        changed price must add a new apartment_price_history row, and the original
        observation must still be there afterward — never overwritten, never lost.
        """
        first_seen = datetime.now(timezone.utc)
        apartment = self._make_apartment(first_seen)

        with self.db.transaction() as conn:
            apartments.insert_apartment(conn, apartment)
            apartments.add_price_history(
                conn,
                ApartmentPriceHistoryEntry(apartment_id=apartment.id, price=1500.0, observed_at=first_seen),
            )

        second_observation = first_seen + timedelta(days=7)
        with self.db.transaction() as conn:
            apartments.update_apartment_state(
                conn,
                apartment_id="apt-1",
                current_price=1450.0,
                current_status="available",
                last_seen_at=second_observation,
            )
            apartments.add_price_history(
                conn,
                ApartmentPriceHistoryEntry(
                    apartment_id=apartment.id, price=1450.0, observed_at=second_observation
                ),
            )

        with self.db.transaction() as conn:
            fetched = apartments.get_apartment(conn, "apt-1")
            price_history = apartments.get_price_history(conn, "apt-1")

        # Current state reflects the latest observation...
        self.assertEqual(fetched.current_price, 1450.0)
        self.assertEqual(fetched.last_seen_at, second_observation)

        # ...but nothing was lost: both observations are still in the history table, in order.
        self.assertEqual(len(price_history), 2)
        self.assertEqual(price_history[0].price, 1500.0)
        self.assertEqual(price_history[1].price, 1450.0)


if __name__ == "__main__":
    unittest.main()
