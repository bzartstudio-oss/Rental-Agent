"""Filter composition — AND/OR/NOT and arbitrary nesting. See
docs/25_Dynamic_Filter_Engine.md "Filter Composition".

Two node types form a tree: `FilterCondition` (a leaf — one filter key + value) and
`FilterGroup` (an operator over a list of children, each itself a `FilterCondition`
or another `FilterGroup`). A flat `SearchRequest.criteria` dict (today's shape,
unchanged since v1.0) is the implicit case — `build_group_from_criteria()` wraps it
as one `AND` group, so every existing caller's "all criteria must match" behavior is
exactly reproduced, not a special case the evaluator has to know about.

Deterministic execution: children are evaluated in list order, and Python lists
preserve insertion order — no sorting step is needed to guarantee this, and none is
added, since one would risk *reordering* an intentional sequence rather than just
guaranteeing repeatability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union

from src.filter_engine.base_filter import FilterContext
from src.filter_engine.exceptions import FilterConfigurationError
from src.filter_engine.factory import FilterFactory
from src.storage.models import Apartment


class FilterOperator(str, Enum):
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass(frozen=True)
class FilterCondition:
    key: str
    value: Any


@dataclass
class FilterGroup:
    """`NOT` is defined over exactly one child (negation of a single condition or
    sub-group) — a multi-child `NOT` is ambiguous (De Morgan's is already expressible
    via nested `AND`/`OR`, so allowing it would be a second way to say the same
    thing, not a new capability) and is rejected by `evaluate()` with
    `FilterConfigurationError`.
    """

    operator: FilterOperator
    children: list["FilterNode"] = field(default_factory=list)


FilterNode = Union[FilterCondition, FilterGroup]


def build_group_from_criteria(criteria: dict[str, Any]) -> FilterGroup:
    """The default, implicit composition for a flat criteria dict — every key must
    match, exactly like `search.criteria.apply_filters()` already requires. Values
    here are expected to already be unwrapped (see `FilterValidator`/`FilterEngine`,
    which call `src.search.criteria.extract_value()` before building conditions).
    """
    return FilterGroup(operator=FilterOperator.AND, children=[FilterCondition(key, value) for key, value in criteria.items()])


def evaluate(node: FilterNode, apartment: Apartment, context: FilterContext) -> tuple[bool, dict[str, bool]]:
    """Returns `(matches, per_filter)` — `per_filter` flattens every leaf condition's
    own result across the whole tree, regardless of nesting, so `FilterResult.per_filter`
    can always explain every individual filter's verdict, not just the composed one.
    """
    if isinstance(node, FilterCondition):
        filter_ = FilterFactory.get(node.key)
        if not filter_.supports(apartment):
            # Not applicable to this apartment at all — never treated as "excluded,"
            # the same "no evidence, never a fabricated no" convention dormant
            # filters use for missing data.
            return True, {node.key: True}
        matched = filter_.apply(apartment, node.value, context)
        return matched, {node.key: matched}

    child_results = [evaluate(child, apartment, context) for child in node.children]
    merged: dict[str, bool] = {}
    for _, per_filter in child_results:
        merged.update(per_filter)
    matches_list = [matched for matched, _ in child_results]

    if node.operator is FilterOperator.AND:
        return all(matches_list) if matches_list else True, merged
    if node.operator is FilterOperator.OR:
        return any(matches_list) if matches_list else True, merged
    if node.operator is FilterOperator.NOT:
        if len(node.children) != 1:
            raise FilterConfigurationError(f"a NOT group must have exactly one child, got {len(node.children)}")
        return not matches_list[0], merged

    raise FilterConfigurationError(f"unknown filter operator: {node.operator!r}")  # pragma: no cover — Enum exhausts above
