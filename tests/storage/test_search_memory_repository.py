"""Round-trip tests for storage/search_memory_repository.py — the v2.0 Step 3 data
access layer for `search_observed_apartments` and the run-stats completion UPDATE.
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.storage import apartment_repository, search_memory_repository, search_repository
from src.storage.database import Database
from src.storage.models import Apartment, SearchRequestRecord


class SearchMemoryRepositoryTestCase(unittest.TestCase):
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

    def _insert_search(self, search_id: str, location: str, created_at: datetime) -> None:
        with self.db.transaction() as conn:
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(
                    id=search_id,
                    created_at=created_at,
                    criteria_json=json.dumps({"location": location, "criteria": {}}),
                ),
            )


class ObservedApartmentsTests(SearchMemoryRepositoryTestCase):
    def test_round_trip_and_append_only(self) -> None:
        self._insert_search("search-1", "Valencia", datetime.now(timezone.utc))

        with self.db.transaction() as conn:
            search_memory_repository.add_observed_apartment(conn, "search-1", "apt-1", datetime.now(timezone.utc))

        with self.db.transaction() as conn:
            ids = search_memory_repository.get_observed_apartment_ids(conn, "search-1")
            entries = search_memory_repository.get_observed_apartments(conn, "search-1")

        self.assertEqual(ids, {"apt-1"})
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].apartment_id, "apt-1")

    def test_repeated_searches_each_get_their_own_row_never_overwritten(self) -> None:
        self._insert_search("search-1", "Valencia", datetime.now(timezone.utc))
        self._insert_search("search-2", "Valencia", datetime.now(timezone.utc) + timedelta(days=1))

        with self.db.transaction() as conn:
            search_memory_repository.add_observed_apartment(conn, "search-1", "apt-1", datetime.now(timezone.utc))
            search_memory_repository.add_observed_apartment(conn, "search-2", "apt-1", datetime.now(timezone.utc))

        with self.db.transaction() as conn:
            first_ids = search_memory_repository.get_observed_apartment_ids(conn, "search-1")
            second_ids = search_memory_repository.get_observed_apartment_ids(conn, "search-2")

        # the same apartment observed in both searches — each search keeps its own row
        self.assertEqual(first_ids, {"apt-1"})
        self.assertEqual(second_ids, {"apt-1"})


class CompleteSearchExecutionTests(SearchMemoryRepositoryTestCase):
    def test_fills_in_every_run_stat_column(self) -> None:
        self._insert_search("search-1", "Valencia", datetime.now(timezone.utc))

        with self.db.transaction() as conn:
            search_memory_repository.complete_search_execution(
                conn,
                "search-1",
                execution_time_ms=1234,
                discovered_platform_ids=["test_platform", "other_platform"],
                searched_platform_ids=["test_platform"],
                apartment_count=5,
                new_apartment_count=2,
                removed_apartment_count=1,
                changed_apartment_count=1,
                report_path="output/search-1.html",
                runtime_stats={"errors": ["other_platform: boom"], "warnings": [], "failed_platform_ids": ["other_platform"], "connector_versions": {}, "pdf_report_path": None},
            )

        with self.db.transaction() as conn:
            record = search_repository.get_search_request(conn, "search-1")

        self.assertEqual(record.execution_time_ms, 1234)
        self.assertEqual(record.discovered_platform_ids, ["test_platform", "other_platform"])
        self.assertEqual(record.searched_platform_ids, ["test_platform"])
        self.assertEqual(record.apartment_count, 5)
        self.assertEqual(record.new_apartment_count, 2)
        self.assertEqual(record.removed_apartment_count, 1)
        self.assertEqual(record.changed_apartment_count, 1)
        self.assertEqual(record.report_path, "output/search-1.html")
        self.assertEqual(record.runtime_stats["errors"], ["other_platform: boom"])


class FindPreviousSearchTests(SearchMemoryRepositoryTestCase):
    def test_returns_none_when_no_earlier_search_exists(self) -> None:
        self._insert_search("search-1", "Valencia", datetime.now(timezone.utc))

        with self.db.transaction() as conn:
            previous = search_memory_repository.find_previous_search(
                conn, "Valencia", before_created_at=datetime.now(timezone.utc), exclude_search_id="search-1"
            )

        self.assertIsNone(previous)

    def test_finds_the_most_recent_earlier_search_for_the_same_location(self) -> None:
        first_seen = datetime.now(timezone.utc)
        self._insert_search("search-1", "Valencia", first_seen)
        self._insert_search("search-2", "Valencia", first_seen + timedelta(days=1))
        self._insert_search("search-3", "Valencia", first_seen + timedelta(days=2))

        with self.db.transaction() as conn:
            previous = search_memory_repository.find_previous_search(
                conn, "Valencia", before_created_at=first_seen + timedelta(days=3), exclude_search_id="search-3"
            )

        self.assertEqual(previous.id, "search-2")  # most recent, not the oldest

    def test_ignores_a_different_location(self) -> None:
        first_seen = datetime.now(timezone.utc)
        self._insert_search("search-1", "Madrid", first_seen)

        with self.db.transaction() as conn:
            previous = search_memory_repository.find_previous_search(
                conn, "Valencia", before_created_at=first_seen + timedelta(days=1), exclude_search_id=None
            )

        self.assertIsNone(previous)

    def test_matches_regardless_of_differing_criteria(self) -> None:
        """docs/17_Search_Memory.md: matched by location, not exact criteria."""
        first_seen = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(
                    id="search-1",
                    created_at=first_seen,
                    criteria_json=json.dumps({"location": "Valencia", "criteria": {"max_price": 1000}}),
                ),
            )

        with self.db.transaction() as conn:
            previous = search_memory_repository.find_previous_search(
                conn, "Valencia", before_created_at=first_seen + timedelta(days=1), exclude_search_id=None
            )

        self.assertEqual(previous.id, "search-1")


class GetSearchHistoryTests(SearchMemoryRepositoryTestCase):
    def test_returns_every_search_newest_first(self) -> None:
        first_seen = datetime.now(timezone.utc)
        self._insert_search("search-1", "Valencia", first_seen)
        self._insert_search("search-2", "Valencia", first_seen + timedelta(days=1))

        with self.db.transaction() as conn:
            history = search_memory_repository.get_search_history(conn)

        self.assertEqual([r.id for r in history], ["search-2", "search-1"])

    def test_filters_by_location(self) -> None:
        first_seen = datetime.now(timezone.utc)
        self._insert_search("search-1", "Valencia", first_seen)
        self._insert_search("search-2", "Madrid", first_seen + timedelta(days=1))

        with self.db.transaction() as conn:
            history = search_memory_repository.get_search_history(conn, location="Madrid")

        self.assertEqual([r.id for r in history], ["search-2"])

    def test_respects_limit(self) -> None:
        first_seen = datetime.now(timezone.utc)
        self._insert_search("search-1", "Valencia", first_seen)
        self._insert_search("search-2", "Valencia", first_seen + timedelta(days=1))
        self._insert_search("search-3", "Valencia", first_seen + timedelta(days=2))

        with self.db.transaction() as conn:
            history = search_memory_repository.get_search_history(conn, location="Valencia", limit=2)

        self.assertEqual([r.id for r in history], ["search-3", "search-2"])


if __name__ == "__main__":
    unittest.main()
