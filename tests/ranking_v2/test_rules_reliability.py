"""Unit tests for PlatformReliabilityRankingRule/ConnectorReliabilityRankingRule —
src/ranking_v2/rules/reliability_rules.py.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.connectors.base import RawListing
from src.discovery import platform_registry
from src.knowledge import knowledge_service
from src.ranking_v2.base_rule import RankingContext
from src.ranking_v2.rules.reliability_rules import ConnectorReliabilityRankingRule, PlatformReliabilityRankingRule
from src.storage import search_repository
from src.storage.database import Database
from src.storage.models import Apartment, Platform, SearchRequestRecord

_COMPLETE_LISTING = RawListing(
    platform_listing_id="l1", title="A place", price=1000, url="u", bedrooms=1, bathrooms=1,
    sqft=500, address_raw="123 Main St", status="available", image_urls=["http://x/1.jpg"],
)


def _apartment() -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id="apt-1", platform_id="p1", platform_listing_id="l1", title="Test", url="u",
        current_price=1000, current_status="available", first_seen_at=now, last_seen_at=now,
    )


class _ReliabilityRuleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn, Platform(id="p1", name="P1", country="N/A", homepage="n/a",
                                connector_available=True, connector_name="p1_connector", created_at=now),
            )
            search_repository.insert_search_request(
                conn, SearchRequestRecord(id="search-1", created_at=now, criteria_json="{}"),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _record_observation(self, conn, failed: bool) -> None:
        knowledge_service.record_platform_observation(
            conn, "p1", "search-1", results_count=5, failed=failed, response_time_ms=100,
            raw_listings=[_COMPLETE_LISTING], ranking_usefulness_score=None, parsing_success=not failed,
            observed_at=datetime.now(timezone.utc),
        )


class PlatformReliabilityRankingRuleTests(_ReliabilityRuleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.rule = PlatformReliabilityRankingRule()

    def test_no_context_is_honest_no_evidence(self) -> None:
        evidence = self.rule.evaluate(_apartment(), RankingContext())
        self.assertIsNone(evidence.raw_score)

    def test_no_observations_yet_is_honest_no_evidence(self) -> None:
        with self.db.transaction() as conn:
            evidence = self.rule.evaluate(_apartment(), RankingContext(conn=conn))
        self.assertIsNone(evidence.raw_score)
        self.assertTrue(evidence.warnings)

    def test_successful_observations_score_well(self) -> None:
        with self.db.transaction() as conn:
            for _ in range(5):
                self._record_observation(conn, failed=False)
            evidence = self.rule.evaluate(_apartment(), RankingContext(conn=conn))
        self.assertGreater(evidence.raw_score, 0.5)
        self.assertEqual(evidence.confidence, 1.0)


class ConnectorReliabilityRankingRuleTests(_ReliabilityRuleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.rule = ConnectorReliabilityRankingRule()

    def test_no_context_is_honest_no_evidence(self) -> None:
        evidence = self.rule.evaluate(_apartment(), RankingContext())
        self.assertIsNone(evidence.raw_score)

    def test_no_observations_yet_is_honest_no_evidence(self) -> None:
        with self.db.transaction() as conn:
            evidence = self.rule.evaluate(_apartment(), RankingContext(conn=conn))
        self.assertIsNone(evidence.raw_score)

    def test_all_successful_runs_score_perfectly(self) -> None:
        with self.db.transaction() as conn:
            for _ in range(3):
                self._record_observation(conn, failed=False)
            evidence = self.rule.evaluate(_apartment(), RankingContext(conn=conn))
        self.assertEqual(evidence.raw_score, 1.0)
        self.assertIn("3/3", evidence.detail)

    def test_mixed_results_score_proportionally(self) -> None:
        with self.db.transaction() as conn:
            self._record_observation(conn, failed=False)
            self._record_observation(conn, failed=True)
            evidence = self.rule.evaluate(_apartment(), RankingContext(conn=conn))
        self.assertEqual(evidence.raw_score, 0.5)


if __name__ == "__main__":
    unittest.main()
