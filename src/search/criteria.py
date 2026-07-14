"""The extensible filter/criteria registry — see docs/04_Search_Request.md "Design:
Configurable and Extensible". Each registered FilterDefinition is the single place that
knows how one criterion (e.g. "max_price") validates, hard-filters, and optionally scores
an apartment. Adding a new filter type means adding one entry here — nothing in
SearchRequest, connectors, or the ranking engine's core loop needs to change.

Hard filter vs. score (docs/08_Ranking_System.md): `matches` is a pass/fail cutoff applied
before ranking; `score` (optional) is how much a *passing* apartment's exact value should
move it up or down the order. A filter can have `matches` only (e.g. min_bedrooms is a
cutoff with nothing more to say once satisfied).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.storage.models import Apartment


@dataclass
class FilterDefinition:
    key: str
    validate: Callable[[object], None]
    matches: Callable[[Apartment, object], bool]
    score: Callable[[Apartment, object], float] | None = None


_REGISTRY: dict[str, FilterDefinition] = {}


def register(definition: FilterDefinition) -> None:
    _REGISTRY[definition.key] = definition


def get_filter(key: str) -> FilterDefinition:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(f"{key!r} is not a registered search filter. Registered: {sorted(_REGISTRY)}") from None


def registered_keys() -> list[str]:
    return sorted(_REGISTRY)


def extract_value(raw_value: object) -> object:
    """A criterion value in SearchRequest.criteria is either a bare value (e.g. `1200`)
    or a `{"value": ..., "weight": ...}` wrapper for ranking weight (docs/08_Ranking_System.md
    "Configurability"). Every filter's validate/matches/score functions operate on the
    unwrapped plain value — this is the one place that unwrapping happens.
    """
    if isinstance(raw_value, dict) and "value" in raw_value:
        return raw_value["value"]
    return raw_value


def extract_weight(raw_value: object) -> float:
    if isinstance(raw_value, dict) and "weight" in raw_value:
        return float(raw_value["weight"])
    return 1.0


def validate_criteria(criteria: dict) -> None:
    """Raises for any key without a registered filter, or any (unwrapped) value that
    filter's own validator rejects. Called from SearchRequest.__post_init__ so an invalid
    request fails immediately, not deep in the pipeline (docs/04_Search_Request.md "Lifecycle").
    """
    for key, raw_value in criteria.items():
        get_filter(key).validate(extract_value(raw_value))


def apply_filters(apartments: list[Apartment], criteria: dict) -> list[Apartment]:
    """The hard-filter pass: keep only apartments matching every criterion. Used by
    ranking/ranking_engine.py before scoring.
    """
    return [
        apartment
        for apartment in apartments
        if all(get_filter(key).matches(apartment, extract_value(raw_value)) for key, raw_value in criteria.items())
    ]


def _require_non_negative_number(value: object) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"expected a non-negative number, got {value!r}")


def _ratio_below_budget(apartment: Apartment, budget: float) -> float:
    if not budget:
        return 0.0
    return max(0.0, min(1.0, (budget - apartment.current_price) / budget))


def _ratio_above_minimum(actual: float, minimum: float) -> float:
    if not minimum:
        return 0.0
    return max(0.0, min(1.0, (actual - minimum) / minimum))


register(
    FilterDefinition(
        key="max_price",
        validate=_require_non_negative_number,
        matches=lambda apartment, value: apartment.current_price <= value,
        score=lambda apartment, value: _ratio_below_budget(apartment, value),
    )
)

register(
    FilterDefinition(
        key="min_price",
        validate=_require_non_negative_number,
        matches=lambda apartment, value: apartment.current_price >= value,
    )
)

register(
    FilterDefinition(
        key="min_bedrooms",
        validate=_require_non_negative_number,
        matches=lambda apartment, value: (apartment.bedrooms or 0) >= value,
    )
)

register(
    FilterDefinition(
        key="min_bathrooms",
        validate=_require_non_negative_number,
        matches=lambda apartment, value: (apartment.bathrooms or 0) >= value,
    )
)

register(
    FilterDefinition(
        key="min_sqft",
        validate=_require_non_negative_number,
        matches=lambda apartment, value: (apartment.sqft or 0) >= value,
        score=lambda apartment, value: _ratio_above_minimum(apartment.sqft or 0, value),
    )
)
