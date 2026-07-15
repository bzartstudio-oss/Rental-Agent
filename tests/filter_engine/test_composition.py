"""Unit tests for filter composition — src/filter_engine/composition.py. Uses small
scripted fake filters (registered into an isolated `_FakeRegistry`-backed
`FilterFactory` substitute) rather than the real 39 built-in filters, so these tests
exercise AND/OR/NOT/nesting logic in isolation from any real filter's own behavior.
"""

from __future__ import annotations

import contextlib
import unittest
from unittest.mock import patch

from src.filter_engine.base_filter import BaseFilter, FilterContext
from src.filter_engine.composition import (
    FilterCondition,
    FilterGroup,
    FilterOperator,
    build_group_from_criteria,
    evaluate,
)
from src.filter_engine.exceptions import FilterConfigurationError
from src.filter_engine.metadata import FilterMetadata
from src.filter_engine.registry import FilterRegistry
from src.storage.models import Apartment


class _FakeRegistry(FilterRegistry):
    _filters: dict = {}


class _AlwaysFilter(BaseFilter):
    """Always returns a fixed True/False, regardless of value — a pure boolean
    building block for testing composition logic itself.
    """

    def __init__(self, key: str, result: bool, supports_result: bool = True) -> None:
        self.key = key
        self._result = result
        self._supports_result = supports_result

    def validate(self, value) -> None:
        pass

    def apply(self, apartment: Apartment, value, context: FilterContext) -> bool:
        return self._result

    def supports(self, apartment: Apartment) -> bool:
        return self._supports_result

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(key=self.key, display_name=self.key, category="test", value_type="boolean")


def _apartment() -> Apartment:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return Apartment(
        id="a1", platform_id="p", platform_listing_id="1", title="x", url="x",
        current_price=1000, current_status="available", first_seen_at=now, last_seen_at=now,
    )


class CompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRegistry.reset()
        self._patch = _patch_factory_registry(_FakeRegistry)
        self._patch.__enter__()

    def tearDown(self) -> None:
        self._patch.__exit__(None, None, None)

    def test_and_group_requires_every_child_to_match(self) -> None:
        _FakeRegistry.register(_AlwaysFilter("t", True))
        _FakeRegistry.register(_AlwaysFilter("f", False))
        group = FilterGroup(FilterOperator.AND, [FilterCondition("t", None), FilterCondition("f", None)])

        matches, per_filter = evaluate(group, _apartment(), FilterContext())

        self.assertFalse(matches)
        self.assertEqual(per_filter, {"t": True, "f": False})

    def test_or_group_requires_at_least_one_child_to_match(self) -> None:
        _FakeRegistry.register(_AlwaysFilter("t", True))
        _FakeRegistry.register(_AlwaysFilter("f", False))
        group = FilterGroup(FilterOperator.OR, [FilterCondition("t", None), FilterCondition("f", None)])

        matches, _ = evaluate(group, _apartment(), FilterContext())
        self.assertTrue(matches)

    def test_not_group_negates_its_single_child(self) -> None:
        _FakeRegistry.register(_AlwaysFilter("t", True))
        group = FilterGroup(FilterOperator.NOT, [FilterCondition("t", None)])

        matches, _ = evaluate(group, _apartment(), FilterContext())
        self.assertFalse(matches)

    def test_not_group_with_multiple_children_raises(self) -> None:
        _FakeRegistry.register(_AlwaysFilter("t", True))
        _FakeRegistry.register(_AlwaysFilter("f", False))
        group = FilterGroup(FilterOperator.NOT, [FilterCondition("t", None), FilterCondition("f", None)])

        with self.assertRaises(FilterConfigurationError):
            evaluate(group, _apartment(), FilterContext())

    def test_nested_groups_compose_correctly(self) -> None:
        # (t AND f) OR (NOT f)  ==  False OR True  ==  True
        _FakeRegistry.register(_AlwaysFilter("t", True))
        _FakeRegistry.register(_AlwaysFilter("f", False))
        inner_and = FilterGroup(FilterOperator.AND, [FilterCondition("t", None), FilterCondition("f", None)])
        inner_not = FilterGroup(FilterOperator.NOT, [FilterCondition("f", None)])
        outer = FilterGroup(FilterOperator.OR, [inner_and, inner_not])

        matches, per_filter = evaluate(outer, _apartment(), FilterContext())

        self.assertTrue(matches)
        self.assertEqual(per_filter, {"t": True, "f": False})  # flattened across both nesting levels

    def test_unsupported_filter_never_excludes(self) -> None:
        _FakeRegistry.register(_AlwaysFilter("unsupported", False, supports_result=False))
        group = build_group_from_criteria({"unsupported": None})

        matches, per_filter = evaluate(group, _apartment(), FilterContext())

        self.assertTrue(matches)  # not applicable -> never treated as excluded
        self.assertEqual(per_filter, {"unsupported": True})

    def test_build_group_from_criteria_is_an_implicit_and(self) -> None:
        _FakeRegistry.register(_AlwaysFilter("t", True))
        _FakeRegistry.register(_AlwaysFilter("f", False))
        group = build_group_from_criteria({"t": None, "f": None})

        self.assertEqual(group.operator, FilterOperator.AND)
        matches, _ = evaluate(group, _apartment(), FilterContext())
        self.assertFalse(matches)

    def test_empty_and_group_matches_by_default(self) -> None:
        matches, _ = evaluate(FilterGroup(FilterOperator.AND, []), _apartment(), FilterContext())
        self.assertTrue(matches)

    def test_empty_or_group_matches_by_default(self) -> None:
        matches, _ = evaluate(FilterGroup(FilterOperator.OR, []), _apartment(), FilterContext())
        self.assertTrue(matches)

    def test_deterministic_execution_order(self) -> None:
        """Children are visited in list order — proven by an execution-order log a
        side-effecting fake filter appends to, not just by the boolean outcome.
        """
        order: list[str] = []

        class _LoggingFilter(_AlwaysFilter):
            def apply(self, apartment, value, context):
                order.append(self.key)
                return super().apply(apartment, value, context)

        _FakeRegistry.register(_LoggingFilter("first", True))
        _FakeRegistry.register(_LoggingFilter("second", True))
        _FakeRegistry.register(_LoggingFilter("third", True))
        group = FilterGroup(
            FilterOperator.AND,
            [FilterCondition("first", None), FilterCondition("second", None), FilterCondition("third", None)],
        )

        for _ in range(5):
            order.clear()
            evaluate(group, _apartment(), FilterContext())
            self.assertEqual(order, ["first", "second", "third"])


@contextlib.contextmanager
def _patch_factory_registry(fake_registry):
    """Redirects `FilterFactory.get()` (used internally by `evaluate()`) to the
    isolated fake registry for the duration of one test.
    """
    with patch("src.filter_engine.composition.FilterFactory.get", side_effect=lambda key: fake_registry.get(key)):
        yield


if __name__ == "__main__":
    unittest.main()
