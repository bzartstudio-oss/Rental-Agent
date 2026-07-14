import unittest
from datetime import datetime, timezone

from src.search import criteria
from src.storage.models import Apartment


def _apartment(**overrides) -> Apartment:
    defaults = dict(
        id="apt-1",
        platform_id="test_platform",
        platform_listing_id="listing-1",
        title="Test listing",
        url="https://example.com/1",
        current_price=1000.0,
        current_status="available",
        first_seen_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        bedrooms=2.0,
        bathrooms=1.0,
        sqft=800.0,
    )
    defaults.update(overrides)
    return Apartment(**defaults)


class CriteriaRegistryTests(unittest.TestCase):
    def test_max_price_matches_and_scores(self) -> None:
        cheap = _apartment(current_price=500.0)
        expensive = _apartment(current_price=1500.0)
        definition = criteria.get_filter("max_price")

        self.assertTrue(definition.matches(cheap, 1000.0))
        self.assertFalse(definition.matches(expensive, 1000.0))
        self.assertGreater(definition.score(cheap, 1000.0), 0.0)

    def test_min_bedrooms_treats_missing_data_as_zero(self) -> None:
        no_data = _apartment(bedrooms=None)
        definition = criteria.get_filter("min_bedrooms")
        self.assertFalse(definition.matches(no_data, 1))

    def test_apply_filters_keeps_only_matching_apartments(self) -> None:
        apartments = [_apartment(id="a", current_price=900.0), _apartment(id="b", current_price=1400.0)]

        result = criteria.apply_filters(apartments, {"max_price": 1000.0})

        self.assertEqual([a.id for a in result], ["a"])

    def test_unregistered_key_raises(self) -> None:
        with self.assertRaises(KeyError):
            criteria.get_filter("not_a_real_filter")

    def test_validate_criteria_rejects_negative_value(self) -> None:
        with self.assertRaises(ValueError):
            criteria.validate_criteria({"max_price": -100})

    def test_validate_criteria_rejects_unregistered_key(self) -> None:
        with self.assertRaises(KeyError):
            criteria.validate_criteria({"not_a_real_filter": 1})


if __name__ == "__main__":
    unittest.main()
