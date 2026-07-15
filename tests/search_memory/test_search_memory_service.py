"""Tests for src/search_memory/search_memory_service.py — the write side
(record_completed_search) and read side (latest_search/search_history/search_timeline/
compare_searches/average_execution_time/average_apartment_count/search_statistics).
Uses a real temporary SQLite database, never the real data/rental_intelligence.db.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.search.search_request import SearchRequest
from src.search_memory import search_memory_service
from src.storage import apartment_repository, search_memory_repository, search_repository
from src.storage.models import (
    Apartment,
    ApartmentAvailabilityHistoryEntry,
    ApartmentPriceHistoryEntry,
    SearchRequestRecord,
)
from src.storage.database import Database


class SearchMemoryServiceTestCase(unittest.TestCase):
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

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _insert_apartment(self, apartment_id: str, when: datetime, price: float, status: str = "available") -> None:
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(
                conn,
                Apartment(
                    id=apartment_id,
                    platform_id="test_platform",
                    platform_listing_id=apartment_id,
                    title=f"Listing {apartment_id}",
                    url=f"https://example.com/{apartment_id}",
                    current_price=price,
                    current_status=status,
                    first_seen_at=when,
                    last_seen_at=when,
                ),
            )

    def _insert_search_request(self, search_id: str, location: str, created_at: datetime) -> SearchRequest:
        request = SearchRequest(location=location, id=search_id, created_at=created_at)
        with self.db.transaction() as conn:
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(
                    id=request.id, created_at=request.created_at, criteria_json=request.to_criteria_json()
                ),
            )
        return request

    def _observe(self, search_id: str, apartment_id: str, observed_at: datetime) -> None:
        with self.db.transaction() as conn:
            search_memory_repository.add_observed_apartment(conn, search_id, apartment_id, observed_at)

    def _add_price(self, apartment_id: str, price: float, observed_at: datetime, search_id: str) -> None:
        with self.db.transaction() as conn:
            apartment_repository.add_price_history(
                conn,
                ApartmentPriceHistoryEntry(apartment_id=apartment_id, price=price, observed_at=observed_at, search_id=search_id),
            )

    def _add_availability(self, apartment_id: str, status: str, observed_at: datetime, search_id: str) -> None:
        with self.db.transaction() as conn:
            apartment_repository.add_availability_history(
                conn,
                ApartmentAvailabilityHistoryEntry(
                    apartment_id=apartment_id, status=status, observed_at=observed_at, search_id=search_id
                ),
            )


class RecordCompletedSearchTests(SearchMemoryServiceTestCase):
    def test_first_search_for_a_location_has_no_previous_comparison(self) -> None:
        first_seen = datetime.now(timezone.utc)
        request = self._insert_search_request("search-a", "Valencia", first_seen)
        self._insert_apartment("apt-1", first_seen, 1000.0)
        self._insert_apartment("apt-2", first_seen, 1200.0)
        self._observe("search-a", "apt-1", first_seen)
        self._observe("search-a", "apt-2", first_seen)

        with self.db.transaction() as conn:
            result = search_memory_service.record_completed_search(
                conn, request,
                execution_time_ms=100,
                discovered_platform_ids=["test_platform"],
                searched_platform_ids=["test_platform"],
                connector_versions={"test_platform": None},
                errors=[],
                apartment_count=2,
                report_path="output/search-a.html",
            )

        with self.db.transaction() as conn:
            record = search_repository.get_search_request(conn, "search-a")

        self.assertIsNone(result)
        self.assertEqual(record.new_apartment_count, 2)
        self.assertEqual(record.removed_apartment_count, 0)
        self.assertEqual(record.changed_apartment_count, 0)
        self.assertEqual(record.execution_time_ms, 100)
        self.assertEqual(record.report_path, "output/search-a.html")

    def test_second_search_detects_new_removed_and_changed_apartments(self) -> None:
        first_seen = datetime.now(timezone.utc)
        second_seen = first_seen + timedelta(days=7)

        request_a = self._insert_search_request("search-a", "Valencia", first_seen)
        self._insert_apartment("apt-1", first_seen, 1000.0)
        self._insert_apartment("apt-2", first_seen, 1200.0)
        self._add_price("apt-1", 1000.0, first_seen, "search-a")
        self._add_price("apt-2", 1200.0, first_seen, "search-a")
        self._add_availability("apt-1", "available", first_seen, "search-a")
        self._observe("search-a", "apt-1", first_seen)
        self._observe("search-a", "apt-2", first_seen)

        with self.db.transaction() as conn:
            search_memory_service.record_completed_search(
                conn, request_a,
                execution_time_ms=100,
                discovered_platform_ids=["test_platform"],
                searched_platform_ids=["test_platform"],
                connector_versions={"test_platform": None},
                errors=[],
                apartment_count=2,
                report_path="output/search-a.html",
            )

        # apt-1 survives (price + status change), apt-2 disappears, apt-3 is new
        request_b = self._insert_search_request("search-b", "Valencia", second_seen)
        self._insert_apartment("apt-3", second_seen, 800.0)
        self._add_price("apt-1", 900.0, second_seen, "search-b")
        self._add_availability("apt-1", "waitlist", second_seen, "search-b")
        self._add_price("apt-3", 800.0, second_seen, "search-b")
        self._observe("search-b", "apt-1", second_seen)
        self._observe("search-b", "apt-3", second_seen)

        with self.db.transaction() as conn:
            comparison = search_memory_service.record_completed_search(
                conn, request_b,
                execution_time_ms=150,
                discovered_platform_ids=["test_platform"],
                searched_platform_ids=["test_platform"],
                connector_versions={"test_platform": None},
                errors=[],
                apartment_count=2,
                report_path="output/search-b.html",
            )

        with self.db.transaction() as conn:
            record_b = search_repository.get_search_request(conn, "search-b")

        self.assertEqual(record_b.new_apartment_count, 1)
        self.assertEqual(record_b.removed_apartment_count, 1)
        self.assertEqual(record_b.changed_apartment_count, 1)

        self.assertEqual(comparison.previous_search_id, "search-a")
        self.assertEqual(comparison.current_search_id, "search-b")
        self.assertEqual(comparison.new_apartment_ids, ["apt-3"])
        self.assertEqual(comparison.removed_apartment_ids, ["apt-2"])
        self.assertEqual(comparison.changed_apartment_ids, ["apt-1"])
        self.assertEqual(len(comparison.price_changes), 1)
        self.assertEqual(comparison.price_changes[0].apartment_id, "apt-1")
        self.assertEqual(comparison.price_changes[0].old_price, 1000.0)
        self.assertEqual(comparison.price_changes[0].new_price, 900.0)
        self.assertEqual(len(comparison.availability_changes), 1)
        self.assertEqual(comparison.availability_changes[0].old_status, "available")
        self.assertEqual(comparison.availability_changes[0].new_status, "waitlist")
        self.assertEqual(comparison.execution_time_delta_ms, 50)
        self.assertEqual(comparison.connector_failures, [])
        self.assertEqual(comparison.platform_coverage_change.newly_searched_platform_ids, [])
        self.assertEqual(comparison.platform_coverage_change.no_longer_searched_platform_ids, [])
        self.assertEqual(comparison.search_quality_delta, 0.0)

    def test_repeated_identical_search_reports_zero_change_and_stays_append_only(self) -> None:
        first_seen = datetime.now(timezone.utc)
        second_seen = first_seen + timedelta(days=1)

        request_a = self._insert_search_request("search-a", "Valencia", first_seen)
        self._insert_apartment("apt-1", first_seen, 1000.0)
        self._observe("search-a", "apt-1", first_seen)
        with self.db.transaction() as conn:
            search_memory_service.record_completed_search(
                conn, request_a, execution_time_ms=100, discovered_platform_ids=["test_platform"],
                searched_platform_ids=["test_platform"], connector_versions={}, errors=[],
                apartment_count=1, report_path="output/a.html",
            )

        request_b = self._insert_search_request("search-b", "Valencia", second_seen)
        self._observe("search-b", "apt-1", second_seen)  # same apartment, nothing changed
        with self.db.transaction() as conn:
            comparison = search_memory_service.record_completed_search(
                conn, request_b, execution_time_ms=100, discovered_platform_ids=["test_platform"],
                searched_platform_ids=["test_platform"], connector_versions={}, errors=[],
                apartment_count=1, report_path="output/b.html",
            )

        self.assertEqual(comparison.new_apartment_ids, [])
        self.assertEqual(comparison.removed_apartment_ids, [])
        self.assertEqual(comparison.changed_apartment_ids, [])

        with self.db.transaction() as conn:
            search_a_ids = search_memory_repository.get_observed_apartment_ids(conn, "search-a")
            search_b_ids = search_memory_repository.get_observed_apartment_ids(conn, "search-b")

        # both searches' own observed rows still exist independently — never merged/overwritten
        self.assertEqual(search_a_ids, {"apt-1"})
        self.assertEqual(search_b_ids, {"apt-1"})

    def test_connector_failure_is_recorded_in_runtime_stats(self) -> None:
        first_seen = datetime.now(timezone.utc)
        request = self._insert_search_request("search-a", "Valencia", first_seen)

        with self.db.transaction() as conn:
            search_memory_service.record_completed_search(
                conn, request, execution_time_ms=50,
                discovered_platform_ids=["test_platform", "broken_platform"],
                searched_platform_ids=["test_platform"],
                connector_versions={"test_platform": None},
                errors=["broken_platform: connection refused"],
                apartment_count=0, report_path="output/a.html",
            )

        with self.db.transaction() as conn:
            record = search_repository.get_search_request(conn, "search-a")

        self.assertEqual(record.runtime_stats["failed_platform_ids"], ["broken_platform"])
        self.assertEqual(record.runtime_stats["errors"], ["broken_platform: connection refused"])


class ReadSideTests(SearchMemoryServiceTestCase):
    def _complete(self, request: SearchRequest, execution_time_ms: int, apartment_count: int) -> None:
        with self.db.transaction() as conn:
            search_memory_service.record_completed_search(
                conn, request, execution_time_ms=execution_time_ms,
                discovered_platform_ids=["test_platform"], searched_platform_ids=["test_platform"],
                connector_versions={}, errors=[], apartment_count=apartment_count,
                report_path=f"output/{request.id}.html",
            )

    def test_latest_search_and_search_history_are_newest_first(self) -> None:
        first_seen = datetime.now(timezone.utc)
        request_a = self._insert_search_request("search-a", "Valencia", first_seen)
        self._complete(request_a, 100, 2)
        request_b = self._insert_search_request("search-b", "Valencia", first_seen + timedelta(days=1))
        self._complete(request_b, 150, 3)

        with self.db.transaction() as conn:
            latest = search_memory_service.latest_search(conn, "Valencia")
            history = search_memory_service.search_history(conn, "Valencia")

        self.assertEqual(latest.id, "search-b")
        self.assertEqual([e.id for e in history], ["search-b", "search-a"])

    def test_search_timeline_is_oldest_first(self) -> None:
        first_seen = datetime.now(timezone.utc)
        request_a = self._insert_search_request("search-a", "Valencia", first_seen)
        self._complete(request_a, 100, 2)
        request_b = self._insert_search_request("search-b", "Valencia", first_seen + timedelta(days=1))
        self._complete(request_b, 150, 3)

        with self.db.transaction() as conn:
            timeline = search_memory_service.search_timeline(conn, "Valencia")

        self.assertEqual(timeline.location, "Valencia")
        self.assertEqual([e.id for e in timeline.executions], ["search-a", "search-b"])

    def test_compare_searches_is_order_independent(self) -> None:
        first_seen = datetime.now(timezone.utc)
        request_a = self._insert_search_request("search-a", "Valencia", first_seen)
        self._insert_apartment("apt-1", first_seen, 1000.0)
        self._observe("search-a", "apt-1", first_seen)
        self._complete(request_a, 100, 1)

        request_b = self._insert_search_request("search-b", "Valencia", first_seen + timedelta(days=1))
        self._observe("search-b", "apt-1", first_seen + timedelta(days=1))
        self._complete(request_b, 120, 1)

        with self.db.transaction() as conn:
            forward = search_memory_service.compare_searches(conn, "search-a", "search-b")
            backward = search_memory_service.compare_searches(conn, "search-b", "search-a")

        self.assertEqual(forward.previous_search_id, "search-a")
        self.assertEqual(forward.current_search_id, "search-b")
        self.assertEqual(backward.previous_search_id, forward.previous_search_id)
        self.assertEqual(backward.current_search_id, forward.current_search_id)

    def test_average_execution_time_and_apartment_count(self) -> None:
        first_seen = datetime.now(timezone.utc)
        request_a = self._insert_search_request("search-a", "Valencia", first_seen)
        self._complete(request_a, 100, 2)
        request_b = self._insert_search_request("search-b", "Valencia", first_seen + timedelta(days=1))
        self._complete(request_b, 200, 4)

        with self.db.transaction() as conn:
            avg_time = search_memory_service.average_execution_time(conn, "Valencia")
            avg_count = search_memory_service.average_apartment_count(conn, "Valencia")
            stats = search_memory_service.search_statistics(conn, "Valencia")

        self.assertEqual(avg_time, 150.0)
        self.assertEqual(avg_count, 3.0)
        self.assertEqual(stats.search_count, 2)
        self.assertEqual(stats.average_execution_time_ms, 150.0)
        self.assertEqual(stats.average_apartment_count, 3.0)

    def test_statistics_with_no_search_history_are_all_none(self) -> None:
        with self.db.transaction() as conn:
            stats = search_memory_service.search_statistics(conn, "Nowhere")

        self.assertEqual(stats.search_count, 0)
        self.assertIsNone(stats.average_execution_time_ms)
        self.assertIsNone(stats.average_apartment_count)


if __name__ == "__main__":
    unittest.main()
