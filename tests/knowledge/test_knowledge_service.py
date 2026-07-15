"""Tests for src/knowledge/knowledge_service.py — the write side
(record_platform_observation, including rollup recomputation over the recent window)
and the read side (platform_reliability/platform_statistics/best_platforms/
connector_health/average_city_price/city_statistics/knowledge_summary). Uses a real
temporary SQLite database, never the real data/rental_intelligence.db.
"""

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.connectors.base import RawListing
from src.discovery import platform_registry
from src.knowledge import knowledge_service
from src.storage import apartment_repository, search_memory_repository, search_repository
from src.storage.database import Database
from src.storage.models import Apartment, Platform, SearchRequestRecord


class KnowledgeServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="test_platform", name="Test Platform", country="Testland",
                    homepage="https://example.com", connector_available=True,
                    connector_name="test_platform", created_at=datetime.now(timezone.utc),
                ),
            )
            platform_registry.register_platform(
                conn,
                Platform(
                    id="other_platform", name="Other Platform", country="Testland",
                    homepage="https://example.org", connector_available=True,
                    connector_name="other_platform", created_at=datetime.now(timezone.utc),
                ),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _raw_listings(self, count=3, with_images=True) -> list[RawListing]:
        return [
            RawListing(
                platform_listing_id=f"l{i}", title=f"Listing {i}", price=1000.0 + i, url=f"https://example.com/{i}",
                bedrooms=2.0, bathrooms=1.0, sqft=800.0, address_raw="123 Main St", status="available",
                image_urls=["a.jpg"] if with_images else [],
            )
            for i in range(count)
        ]

    def _insert_search(self, search_id: str, location: str = "Example City", created_at=None) -> None:
        with self.db.transaction() as conn:
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(
                    id=search_id, created_at=created_at or datetime.now(timezone.utc),
                    criteria_json=json.dumps({"location": location, "criteria": {}}),
                ),
            )


class RecordPlatformObservationTests(KnowledgeServiceTestCase):
    def test_successful_observation_is_recorded_and_rollups_update(self) -> None:
        self._insert_search("search-1")
        with self.db.transaction() as conn:
            knowledge_service.record_platform_observation(
                conn, "test_platform", "search-1",
                results_count=3, failed=False, response_time_ms=500,
                raw_listings=self._raw_listings(), ranking_usefulness_score=1.5,
                parsing_success=True, observed_at=datetime.now(timezone.utc),
            )

        with self.db.transaction() as conn:
            platform = platform_registry.get_platform(conn, "test_platform")

        self.assertEqual(platform.success_rate, 1.0)
        self.assertEqual(platform.avg_response_time_ms, 500)
        self.assertEqual(platform.avg_apartment_count, 3)
        self.assertIsNotNone(platform.reliability_score)
        self.assertGreater(platform.reliability_score, 0)

    def test_failed_observation_has_null_quality_scores_and_lowers_success_rate(self) -> None:
        self._insert_search("search-1")
        with self.db.transaction() as conn:
            knowledge_service.record_platform_observation(
                conn, "test_platform", "search-1", results_count=3, failed=False,
                response_time_ms=500, raw_listings=self._raw_listings(),
                ranking_usefulness_score=1.0, parsing_success=True, observed_at=datetime.now(timezone.utc),
            )

        self._insert_search("search-2")
        with self.db.transaction() as conn:
            knowledge_service.record_platform_observation(
                conn, "test_platform", "search-2", results_count=0, failed=True,
                response_time_ms=200, raw_listings=None, ranking_usefulness_score=None,
                parsing_success=False, observed_at=datetime.now(timezone.utc),
            )

        with self.db.transaction() as conn:
            platform = platform_registry.get_platform(conn, "test_platform")

        self.assertEqual(platform.success_rate, 0.5)  # 1 of 2 succeeded

    def test_observations_never_overwrite_each_other(self) -> None:
        for i in range(3):
            self._insert_search(f"search-{i}")
            with self.db.transaction() as conn:
                knowledge_service.record_platform_observation(
                    conn, "test_platform", f"search-{i}", results_count=i, failed=False,
                    response_time_ms=100, raw_listings=self._raw_listings(count=1),
                    ranking_usefulness_score=1.0, parsing_success=True, observed_at=datetime.now(timezone.utc),
                )

        with self.db.transaction() as conn:
            knowledge = knowledge_service.platform_reliability(conn, "test_platform")

        self.assertEqual(knowledge.observation_count, 3)

    def test_rollups_are_computed_over_the_recent_window_only(self) -> None:
        """docs/16_Knowledge_Engine.md: recent window (last 20), not an all-time
        average — five old, very-slow observations must not drag down a platform
        that's been fast for its last 20 searches.
        """
        first_seen = datetime.now(timezone.utc)
        for i in range(5):
            self._insert_search(f"old-search-{i}", created_at=first_seen + timedelta(minutes=i))
        for i in range(20):
            self._insert_search(f"new-search-{i}", created_at=first_seen + timedelta(minutes=10 + i))

        with self.db.transaction() as conn:
            for i in range(5):
                knowledge_service.record_platform_observation(
                    conn, "test_platform", f"old-search-{i}", results_count=1, failed=False,
                    response_time_ms=9999, raw_listings=self._raw_listings(count=1),
                    ranking_usefulness_score=1.0, parsing_success=True,
                    observed_at=first_seen + timedelta(minutes=i),
                )
            for i in range(20):
                knowledge_service.record_platform_observation(
                    conn, "test_platform", f"new-search-{i}", results_count=1, failed=False,
                    response_time_ms=100, raw_listings=self._raw_listings(count=1),
                    ranking_usefulness_score=1.0, parsing_success=True,
                    observed_at=first_seen + timedelta(minutes=10 + i),
                )

        with self.db.transaction() as conn:
            platform = platform_registry.get_platform(conn, "test_platform")

        self.assertEqual(platform.avg_response_time_ms, 100)  # not blended with the 9999s


class ReadSideTests(KnowledgeServiceTestCase):
    def _observe(self, platform_id: str, search_id: str, **overrides) -> None:
        defaults = dict(
            results_count=3, failed=False, response_time_ms=500, raw_listings=self._raw_listings(),
            ranking_usefulness_score=1.0, parsing_success=True, observed_at=datetime.now(timezone.utc),
        )
        defaults.update(overrides)
        with self.db.transaction() as conn:
            knowledge_service.record_platform_observation(conn, platform_id, search_id, **defaults)

    def test_platform_reliability_reflects_last_successful_and_failed_search(self) -> None:
        first_seen = datetime.now(timezone.utc)
        self._insert_search("search-1")
        self._observe("test_platform", "search-1", observed_at=first_seen, failed=False)
        self._insert_search("search-2")
        self._observe(
            "test_platform", "search-2", observed_at=first_seen + timedelta(minutes=1),
            failed=True, results_count=0, raw_listings=None, ranking_usefulness_score=None, parsing_success=False,
        )

        with self.db.transaction() as conn:
            knowledge = knowledge_service.platform_reliability(conn, "test_platform")

        self.assertEqual(knowledge.last_successful_search_at, first_seen)
        self.assertEqual(knowledge.last_failed_search_at, first_seen + timedelta(minutes=1))

    def test_platform_reliability_raises_for_unknown_platform(self) -> None:
        with self.db.transaction() as conn:
            with self.assertRaises(KeyError):
                knowledge_service.platform_reliability(conn, "does_not_exist")

    def test_platform_statistics_returns_every_platform(self) -> None:
        with self.db.transaction() as conn:
            all_platforms = knowledge_service.platform_statistics(conn)

        self.assertEqual({p.platform_id for p in all_platforms}, {"test_platform", "other_platform"})

    def test_best_platforms_ranks_by_reliability_descending(self) -> None:
        self._insert_search("search-1")
        self._observe("test_platform", "search-1", ranking_usefulness_score=1.0)
        self._insert_search("search-2")
        self._observe(
            "other_platform", "search-2", raw_listings=self._raw_listings(with_images=False),
            ranking_usefulness_score=0.1,
        )

        with self.db.transaction() as conn:
            ranked = knowledge_service.best_platforms(conn)

        self.assertEqual(ranked[0].platform_id, "test_platform")

    def test_best_platforms_sorts_unrated_platforms_last(self) -> None:
        self._insert_search("search-1")
        self._observe("test_platform", "search-1")
        # other_platform has zero observations -> reliability_score is None

        with self.db.transaction() as conn:
            ranked = knowledge_service.best_platforms(conn)

        self.assertEqual([p.platform_id for p in ranked], ["test_platform", "other_platform"])

    def test_best_platforms_can_be_scoped_to_a_location(self) -> None:
        self._insert_search("search-1", location="Valencia")
        with self.db.transaction() as conn:
            search_memory_repository.complete_search_execution(
                conn, "search-1", execution_time_ms=100, discovered_platform_ids=["test_platform"],
                searched_platform_ids=["test_platform"], apartment_count=3, new_apartment_count=3,
                removed_apartment_count=0, changed_apartment_count=0, report_path="x.html", runtime_stats={},
            )
        self._observe("test_platform", "search-1")
        self._insert_search("search-2", location="Madrid")
        with self.db.transaction() as conn:
            search_memory_repository.complete_search_execution(
                conn, "search-2", execution_time_ms=100, discovered_platform_ids=["other_platform"],
                searched_platform_ids=["other_platform"], apartment_count=3, new_apartment_count=3,
                removed_apartment_count=0, changed_apartment_count=0, report_path="x.html", runtime_stats={},
            )
        self._observe("other_platform", "search-2")

        with self.db.transaction() as conn:
            valencia_best = knowledge_service.best_platforms(conn, location="Valencia")

        self.assertEqual([p.platform_id for p in valencia_best], ["test_platform"])

    def test_connector_health_only_lists_platforms_with_observations(self) -> None:
        self._insert_search("search-1")
        self._observe("test_platform", "search-1")

        with self.db.transaction() as conn:
            health = knowledge_service.connector_health(conn)

        self.assertEqual([h.platform_id for h in health], ["test_platform"])
        self.assertEqual(health[0].success_count, 1)
        self.assertEqual(health[0].failure_count, 0)

    def test_average_city_price_and_city_statistics(self) -> None:
        self._insert_search("search-1", location="Valencia")
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(
                conn,
                Apartment(
                    id="apt-1", platform_id="test_platform", platform_listing_id="l1", title="A",
                    url="https://example.com/a", current_price=1000.0, current_status="available",
                    first_seen_at=now, last_seen_at=now,
                ),
            )
            apartment_repository.insert_apartment(
                conn,
                Apartment(
                    id="apt-2", platform_id="test_platform", platform_listing_id="l2", title="B",
                    url="https://example.com/b", current_price=2000.0, current_status="rented",
                    first_seen_at=now, last_seen_at=now,
                ),
            )
            search_memory_repository.add_observed_apartment(conn, "search-1", "apt-1", now)
            search_memory_repository.add_observed_apartment(conn, "search-1", "apt-2", now)
            search_memory_repository.complete_search_execution(
                conn, "search-1", execution_time_ms=100, discovered_platform_ids=["test_platform"],
                searched_platform_ids=["test_platform"], apartment_count=2, new_apartment_count=2,
                removed_apartment_count=0, changed_apartment_count=0, report_path="x.html", runtime_stats={},
            )
        self._observe("test_platform", "search-1")

        with self.db.transaction() as conn:
            avg_price = knowledge_service.average_city_price(conn, "Valencia")
            city = knowledge_service.city_statistics(conn, "Valencia")

        self.assertEqual(avg_price, 1500.0)
        self.assertEqual(city.search_count, 1)
        self.assertEqual(city.avg_price, 1500.0)
        self.assertEqual(city.avg_availability_ratio, 0.5)
        self.assertIn("test_platform", city.most_reliable_platform_ids)

    def test_city_statistics_with_no_searches_returns_empty_stats(self) -> None:
        with self.db.transaction() as conn:
            city = knowledge_service.city_statistics(conn, "Nowhere")

        self.assertEqual(city.search_count, 0)
        self.assertIsNone(city.avg_price)
        self.assertIsNone(city.avg_availability_ratio)

    def test_knowledge_summary_combines_platform_and_search_statistics(self) -> None:
        self._insert_search("search-1")
        with self.db.transaction() as conn:
            search_memory_repository.complete_search_execution(
                conn, "search-1", execution_time_ms=200, discovered_platform_ids=["test_platform"],
                searched_platform_ids=["test_platform"], apartment_count=3, new_apartment_count=3,
                removed_apartment_count=0, changed_apartment_count=0, report_path="x.html", runtime_stats={},
            )
        self._observe("test_platform", "search-1")

        with self.db.transaction() as conn:
            summary = knowledge_service.knowledge_summary(conn)

        self.assertEqual(summary.total_observations, 1)
        self.assertEqual({p.platform_id for p in summary.platforms}, {"test_platform", "other_platform"})
        self.assertEqual(summary.average_search_execution_time_ms, 200.0)
        self.assertEqual(summary.average_search_apartment_count, 3.0)


class PerformanceTests(KnowledgeServiceTestCase):
    def test_platform_reliability_stays_fast_with_a_long_observation_history(self) -> None:
        first_seen = datetime.now(timezone.utc)
        for i in range(500):
            self._insert_search(f"search-{i}", created_at=first_seen + timedelta(seconds=i))

        with self.db.transaction() as conn:
            for i in range(500):
                knowledge_service.record_platform_observation(
                    conn, "test_platform", f"search-{i}", results_count=3, failed=False,
                    response_time_ms=100, raw_listings=self._raw_listings(count=1),
                    ranking_usefulness_score=1.0, parsing_success=True,
                    observed_at=first_seen + timedelta(seconds=i),
                )

        started = time.perf_counter()
        with self.db.transaction() as conn:
            knowledge_service.platform_reliability(conn, "test_platform")
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
