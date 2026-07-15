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


class DynamicFilterEngineFallbackTests(unittest.TestCase):
    """v2.5 Step 9 — get_filter()/validate_criteria()/apply_filters() must transparently
    resolve any of the Dynamic Filter Engine's 39 filters too, not just this module's
    original 5, so SearchRequest construction and RankingEngine.rank()'s existing
    apply_filters() call keep working for either registry without either needing to
    know which one actually owns a given key.
    """

    def test_get_filter_falls_back_to_the_filter_engine_registry(self) -> None:
        definition = criteria.get_filter("currency")
        self.assertEqual(definition.key, "currency")

    def test_original_five_keys_still_resolve_from_this_module_first(self) -> None:
        # min_bedrooms/min_bathrooms/min_sqft have no FilterEngine equivalent under
        # the same key — this module must still be the (only) source for them.
        self.assertTrue(criteria.get_filter("min_bedrooms"))

    def test_apply_filters_works_with_a_filter_engine_only_key(self) -> None:
        matching = _apartment(id="a", currency="USD")
        non_matching = _apartment(id="b", currency="EUR")

        result = criteria.apply_filters([matching, non_matching], {"currency": "USD"})

        self.assertEqual([a.id for a in result], ["a"])

    def test_validate_criteria_accepts_a_filter_engine_only_key(self) -> None:
        criteria.validate_criteria({"property_type": "apartment"})  # must not raise

    def test_validate_criteria_still_rejects_a_genuinely_unknown_key(self) -> None:
        with self.assertRaises(KeyError):
            criteria.validate_criteria({"still_not_a_real_filter": 1})

    def test_dormant_filter_engine_key_never_excludes_via_apply_filters(self) -> None:
        apartments = [_apartment(id="a"), _apartment(id="b")]
        result = criteria.apply_filters(apartments, {"private_bathroom": True})
        self.assertEqual({a.id for a in result}, {"a", "b"})

    def test_registered_keys_includes_both_registries(self) -> None:
        keys = criteria.registered_keys()
        self.assertIn("min_bedrooms", keys)  # this module's own
        self.assertIn("currency", keys)  # Dynamic Filter Engine's
        self.assertEqual(len(keys), len(set(keys)))  # union, no duplicates


if __name__ == "__main__":
    unittest.main()
