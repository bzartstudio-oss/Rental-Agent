"""`FilterValidator` — the single, canonical validation implementation for both entry
points `FilterEngine` supports (a flat criteria dict, or an explicit `FilterGroup`
tree) — `FilterEngine` calls this rather than re-validating itself, so there is
exactly one place that decides what "a valid filter request" means. See
docs/25_Dynamic_Filter_Engine.md "Filter Pipeline".

Reuses `src.search.criteria.extract_value()` (the existing `{"value": ..., "weight":
...}` unwrapping convention `SearchRequest.criteria` already uses) rather than
inventing a second value-shape for the Filter Engine.
"""

from __future__ import annotations

from src.filter_engine.composition import FilterCondition, FilterGroup, FilterOperator, build_group_from_criteria
from src.filter_engine.configuration import FilterConfiguration
from src.filter_engine.exceptions import FilterValidationError
from src.filter_engine.factory import FilterFactory
from src.filter_engine.registry import FilterRegistry
from src.search.criteria import extract_value


class FilterValidator:
    @classmethod
    def validate_criteria(cls, criteria: dict, config: FilterConfiguration | None = None) -> list[str]:
        """Flat-dict entry point — wraps `criteria` as the same implicit-AND group
        `FilterEngine.run()` builds, then validates that tree. Returns every error
        found (empty list = fully valid); never raises itself.
        """
        normalized = {key: extract_value(raw) for key, raw in criteria.items()}
        return cls.validate_group(build_group_from_criteria(normalized), config)

    @classmethod
    def validate_group(cls, node: FilterCondition | FilterGroup, config: FilterConfiguration | None = None) -> list[str]:
        """Composed entry point — walks a `FilterGroup` tree (or a single leaf
        `FilterCondition`) and returns every error found, in deterministic
        (depth-first, list-order) traversal order.
        """
        config = config or FilterConfiguration()
        errors: list[str] = []
        cls._walk(node, config, errors)
        return errors

    @classmethod
    def _walk(cls, node: FilterCondition | FilterGroup, config: FilterConfiguration, errors: list[str]) -> None:
        if isinstance(node, FilterCondition):
            if not FilterRegistry.is_registered(node.key):
                errors.append(f"{node.key!r} is not a registered filter")
                return
            if not config.is_enabled(node.key):
                errors.append(f"{node.key!r} is disabled by the current FilterConfiguration")
                return
            try:
                FilterFactory.get(node.key).validate(node.value)
            except (ValueError, TypeError, FilterValidationError) as exc:
                errors.append(f"{node.key!r}: {exc}")
            return

        if node.operator is FilterOperator.NOT and len(node.children) != 1:
            errors.append(f"a NOT group must have exactly one child, got {len(node.children)}")
        for child in node.children:
            cls._walk(child, config, errors)

    @classmethod
    def validate_strict(cls, criteria: dict, config: FilterConfiguration | None = None) -> None:
        """Raises `FilterValidationError` (joining every error found) instead of
        returning the list.
        """
        errors = cls.validate_criteria(criteria, config)
        if errors:
            raise FilterValidationError("; ".join(errors))

    @classmethod
    def validate_group_strict(cls, node: FilterCondition | FilterGroup, config: FilterConfiguration | None = None) -> None:
        errors = cls.validate_group(node, config)
        if errors:
            raise FilterValidationError("; ".join(errors))
