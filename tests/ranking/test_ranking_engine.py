import unittest
from datetime import datetime, timezone

from src.ranking.ranking_engine import RankingEngine
from src.search.search_request import SearchRequest
from src.storage.models import Apartment


def _apartment(id_: str, price: float, bedrooms: float = 2.0) -> Apartment:
    now = datetime.now(timezone.utc)
    return Apartment(
        id=id_,
        platform_id="test_platform",
        platform_listing_id=id_,
        title=f"Listing {id_}",
        url=f"https://example.com/{id_}",
        current_price=price,
        current_status="available",
        first_seen_at=now,
        last_seen_at=now,
        bedrooms=bedrooms,
    )


class RankingEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RankingEngine()

    def test_apartments_failing_hard_filter_are_excluded(self) -> None:
        apartments = [_apartment("cheap", 900.0), _apartment("expensive", 1500.0)]
        request = SearchRequest(location="Example City", criteria={"max_price": 1000.0})

        ranked = self.engine.rank(apartments, request)

        self.assertEqual([r.apartment.id for r in ranked], ["cheap"])

    def test_cheaper_apartment_ranks_higher_under_a_budget(self) -> None:
        apartments = [_apartment("pricier", 950.0), _apartment("cheapest", 700.0)]
        request = SearchRequest(location="Example City", criteria={"max_price": 1000.0})

        ranked = self.engine.rank(apartments, request)

        self.assertEqual([r.apartment.id for r in ranked], ["cheapest", "pricier"])
        self.assertEqual(ranked[0].rank, 1)
        self.assertEqual(ranked[1].rank, 2)

    def test_score_breakdown_is_populated_for_scored_criteria(self) -> None:
        apartments = [_apartment("a", 800.0)]
        request = SearchRequest(location="Example City", criteria={"max_price": 1000.0})

        ranked = self.engine.rank(apartments, request)

        self.assertIn("max_price", ranked[0].score_breakdown)
        self.assertGreater(ranked[0].score_breakdown["max_price"], 0.0)

    def test_weighted_criterion_changes_ranking(self) -> None:
        apartments = [_apartment("a", 1000.0), _apartment("b", 500.0)]
        # max_price scored at high weight should make "b" (much cheaper) win decisively
        request = SearchRequest(
            location="Example City",
            criteria={"max_price": {"value": 1000.0, "weight": 5.0}},
        )

        ranked = self.engine.rank(apartments, request)

        self.assertEqual(ranked[0].apartment.id, "b")


if __name__ == "__main__":
    unittest.main()
