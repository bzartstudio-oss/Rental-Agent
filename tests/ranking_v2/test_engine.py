"""Unit + Integration tests for RankingEngineV2 — src/ranking_v2/engine.py. Uses the
real, shared `RankingRuleRegistry` (all 12 built-in rules) and a real (temp) database
so `price`/`availability`/`platform_reliability` etc. get real evidence.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.ranking_v2.base_rule import RankingContext
from src.ranking_v2.engine import RankingEngineV2
from src.ranking_v2.profile import RankingProfile
from src.ranking_v2.weights import RankingWeights
from src.storage import apartment_repository
from src.storage.database import Database
from src.storage.models import Apartment, Platform


def _apartment(apartment_id: str, price: float, status: str = "available") -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id=apartment_id, platform_id="p1", platform_listing_id=apartment_id, title=apartment_id,
        url="u", current_price=price, current_status=status, first_seen_at=now, last_seen_at=now,
    )


class RankingEngineV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(id="p1", name="P1", country="N/A", homepage="n/a", connector_available=False,
                          connector_name=None, created_at=now),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_ranks_best_first_by_final_score(self) -> None:
        engine = RankingEngineV2(profile=RankingProfile(name="avail", weights=RankingWeights(values={"availability": 100})))
        apartments = [_apartment("a1", 1000, "delisted"), _apartment("a2", 1000, "available")]

        with self.db.transaction() as conn:
            ranked = engine.rank(apartments, RankingContext(conn=conn))

        self.assertEqual(ranked[0].apartment_id, "a2")
        self.assertEqual(ranked[0].rank, 1)
        self.assertEqual(ranked[1].rank, 2)

    def test_ranking_is_deterministic_across_repeated_runs(self) -> None:
        engine = RankingEngineV2()
        apartments = [_apartment("a1", 1000), _apartment("a2", 1500), _apartment("a3", 800)]

        with self.db.transaction() as conn:
            ranked1 = engine.rank(apartments, RankingContext(conn=conn, location="City"))
            ranked2 = engine.rank(apartments, RankingContext(conn=conn, location="City"))

        self.assertEqual([r.apartment_id for r in ranked1], [r.apartment_id for r in ranked2])

    def test_default_behavior_with_no_context_does_not_crash(self) -> None:
        engine = RankingEngineV2()
        apartments = [_apartment("a1", 1000), _apartment("a2", 2000)]
        ranked = engine.rank(apartments)  # no context at all
        self.assertEqual(len(ranked), 2)
        for entry in ranked:
            self.assertIsInstance(entry.final_score, float)

    def test_different_profiles_produce_different_orderings(self) -> None:
        """"Demonstrate ranking with multiple apartments using different user
        priorities" (the mission's own words) — a price-only profile and an
        availability-only profile must disagree on at least one case where price
        and availability point in opposite directions.
        """
        apartments = [_apartment("cheap_unavailable", 500, "delisted"), _apartment("pricey_available", 5000, "available")]

        price_only = RankingEngineV2(profile=RankingProfile(name="price", weights=RankingWeights(values={"price": 100})))
        availability_only = RankingEngineV2(
            profile=RankingProfile(name="availability", weights=RankingWeights(values={"availability": 100}))
        )

        with self.db.transaction() as conn:
            context = RankingContext(conn=conn, location="City")
            by_price = price_only.rank(apartments, context)
            by_availability = availability_only.rank(apartments, context)

        self.assertEqual(by_availability[0].apartment_id, "pricey_available")
        # Price-only ranking must not simply reproduce the availability ordering —
        # different priorities, different winner.
        self.assertNotEqual(by_price[0].apartment_id, by_availability[0].apartment_id)


if __name__ == "__main__":
    unittest.main()
