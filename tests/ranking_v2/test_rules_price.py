"""Unit tests for PriceRankingRule/PriceHistoryRankingRule — src/ranking_v2/rules/price_rules.py."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.ranking_v2.base_rule import RankingContext
from src.ranking_v2.rules.price_rules import PriceHistoryRankingRule, PriceRankingRule
from src.search.search_request import SearchRequest
from src.search_memory import search_memory_service
from src.storage import apartment_repository, search_memory_repository, search_repository
from src.storage.database import Database
from src.storage.models import Apartment, ApartmentPriceHistoryEntry, Platform, SearchRequestRecord


def _apartment(price: float) -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id="apt-1", platform_id="p1", platform_listing_id="l1", title="Test", url="u",
        current_price=price, current_status="available", first_seen_at=now, last_seen_at=now,
    )


class PriceRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.rule = PriceRankingRule()
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn, Platform(id="p1", name="P1", country="N/A", homepage="n/a",
                                connector_available=False, connector_name=None, created_at=now),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_no_context_is_honest_no_evidence(self) -> None:
        evidence = self.rule.evaluate(_apartment(1000), RankingContext())
        self.assertIsNone(evidence.raw_score)
        self.assertIsNone(evidence.confidence)

    def test_no_city_average_yet_is_honest_no_evidence(self) -> None:
        with self.db.transaction() as conn:
            evidence = self.rule.evaluate(_apartment(1000), RankingContext(conn=conn, location="Nowhere"))
        self.assertIsNone(evidence.raw_score)
        self.assertTrue(evidence.warnings)

    def _seed_city_average(self, location: str, apartment_id: str, price: float) -> None:
        now = datetime.now(timezone.utc)
        request = SearchRequest(location=location)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(
                conn,
                Apartment(id=apartment_id, platform_id="p1", platform_listing_id=apartment_id, title="X",
                          url="u", current_price=price, current_status="available",
                          first_seen_at=now, last_seen_at=now),
            )
            search_repository.insert_search_request(
                conn, SearchRequestRecord(id=request.id, created_at=now, criteria_json=request.to_criteria_json()),
            )
            search_memory_repository.add_observed_apartment(conn, request.id, apartment_id, now)
        with self.db.transaction() as conn:
            search_memory_service.record_completed_search(
                conn, request, execution_time_ms=1, discovered_platform_ids=["p1"],
                searched_platform_ids=["p1"], connector_versions={}, errors=[],
                apartment_count=1, report_path="n/a",
            )

    def test_price_at_average_scores_the_maximum(self) -> None:
        self._seed_city_average("City", "apt-avg", 1000)
        with self.db.transaction() as conn:
            evidence = self.rule.evaluate(_apartment(1000), RankingContext(conn=conn, location="City"))
        self.assertAlmostEqual(evidence.raw_score, 1.0)
        self.assertEqual(evidence.confidence, 1.0)

    def test_price_double_the_average_scores_zero(self) -> None:
        self._seed_city_average("City2", "apt-avg2", 1000)
        with self.db.transaction() as conn:
            evidence = self.rule.evaluate(_apartment(2000), RankingContext(conn=conn, location="City2"))
        self.assertAlmostEqual(evidence.raw_score, 0.0)

    def test_price_below_average_scores_above_the_midpoint(self) -> None:
        self._seed_city_average("City3", "apt-avg3", 1000)
        with self.db.transaction() as conn:
            evidence = self.rule.evaluate(_apartment(500), RankingContext(conn=conn, location="City3"))
        self.assertEqual(evidence.raw_score, 1.0)  # clamped at the max, still a full score


class PriceHistoryRankingRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.rule = PriceHistoryRankingRule()
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn, Platform(id="p1", name="P1", country="N/A", homepage="n/a",
                                connector_available=False, connector_name=None, created_at=now),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_fewer_than_two_observations_is_honest_no_evidence(self) -> None:
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, _apartment(1000))
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1000, observed_at=now),
            )
            evidence = self.rule.evaluate(_apartment(1000), RankingContext(conn=conn))
        self.assertIsNone(evidence.raw_score)

    def test_price_drop_scores_well(self) -> None:
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, _apartment(900))
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1000, observed_at=now - timedelta(days=7)),
            )
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=900, observed_at=now),
            )
            evidence = self.rule.evaluate(_apartment(900), RankingContext(conn=conn))
        self.assertGreater(evidence.raw_score, 0.6)
        self.assertIn("dropped", evidence.detail)

    def test_price_increase_scores_poorly(self) -> None:
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            apartment_repository.insert_apartment(conn, _apartment(1200))
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1000, observed_at=now - timedelta(days=7)),
            )
            apartment_repository.add_price_history(
                conn, ApartmentPriceHistoryEntry(apartment_id="apt-1", price=1200, observed_at=now),
            )
            evidence = self.rule.evaluate(_apartment(1200), RankingContext(conn=conn))
        self.assertLess(evidence.raw_score, 0.5)
        self.assertIn("increased", evidence.detail)


if __name__ == "__main__":
    unittest.main()
