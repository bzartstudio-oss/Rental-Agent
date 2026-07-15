"""Unit tests for FilterValidator — src/filter_engine/validator.py, against the real,
shared FilterRegistry (39 built-in filters already self-registered)."""

from __future__ import annotations

import unittest

from src.filter_engine.composition import FilterCondition, FilterGroup, FilterOperator
from src.filter_engine.configuration import FilterConfiguration
from src.filter_engine.exceptions import FilterValidationError
from src.filter_engine.validator import FilterValidator


class ValidateCriteriaTests(unittest.TestCase):
    def test_valid_criteria_produces_no_errors(self) -> None:
        self.assertEqual(FilterValidator.validate_criteria({"max_price": 2000}), [])

    def test_unregistered_key_is_an_error(self) -> None:
        errors = FilterValidator.validate_criteria({"not_a_real_filter": 1})
        self.assertEqual(len(errors), 1)
        self.assertIn("not_a_real_filter", errors[0])

    def test_invalid_value_is_an_error(self) -> None:
        errors = FilterValidator.validate_criteria({"max_price": -5})
        self.assertEqual(len(errors), 1)
        self.assertIn("max_price", errors[0])

    def test_disabled_filter_is_an_error(self) -> None:
        config = FilterConfiguration(enabled_filter_keys={"min_price"})
        errors = FilterValidator.validate_criteria({"max_price": 2000}, config)
        self.assertEqual(len(errors), 1)
        self.assertIn("disabled", errors[0])

    def test_wrapped_weighted_value_is_unwrapped_before_validation(self) -> None:
        """`{"value": ..., "weight": ...}` — the existing SearchRequest.criteria
        convention — must validate the unwrapped value, not the wrapper dict itself.
        """
        errors = FilterValidator.validate_criteria({"max_price": {"value": 2000, "weight": 2.0}})
        self.assertEqual(errors, [])

    def test_multiple_errors_are_all_reported(self) -> None:
        errors = FilterValidator.validate_criteria({"max_price": -5, "unknown_key": 1})
        self.assertEqual(len(errors), 2)

    def test_validate_strict_raises_when_invalid(self) -> None:
        with self.assertRaises(FilterValidationError):
            FilterValidator.validate_strict({"max_price": -5})

    def test_validate_strict_does_not_raise_when_valid(self) -> None:
        FilterValidator.validate_strict({"max_price": 2000})  # must not raise


class ValidateGroupTests(unittest.TestCase):
    def test_valid_group_produces_no_errors(self) -> None:
        group = FilterGroup(FilterOperator.AND, [FilterCondition("max_price", 2000), FilterCondition("min_price", 500)])
        self.assertEqual(FilterValidator.validate_group(group), [])

    def test_nested_group_errors_are_found_at_any_depth(self) -> None:
        inner = FilterGroup(FilterOperator.OR, [FilterCondition("max_price", -5)])
        outer = FilterGroup(FilterOperator.AND, [FilterCondition("min_price", 500), inner])

        errors = FilterValidator.validate_group(outer)
        self.assertEqual(len(errors), 1)
        self.assertIn("max_price", errors[0])

    def test_not_group_with_wrong_child_count_is_an_error(self) -> None:
        group = FilterGroup(FilterOperator.NOT, [FilterCondition("max_price", 2000), FilterCondition("min_price", 500)])
        errors = FilterValidator.validate_group(group)
        self.assertTrue(any("NOT" in e for e in errors))

    def test_validate_group_strict_raises_when_invalid(self) -> None:
        with self.assertRaises(FilterValidationError):
            FilterValidator.validate_group_strict(FilterGroup(FilterOperator.AND, [FilterCondition("max_price", -5)]))


if __name__ == "__main__":
    unittest.main()
