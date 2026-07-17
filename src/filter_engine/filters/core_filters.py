"""Data-backed built-in filters — every one operates on a real, populated
`Apartment` field (or, for `ImageCountFilter`, a real `apartment_images` row count).
See docs/25_Dynamic_Filter_Engine.md "Built-In Filters".

`_LegacyCriteriaFilter` wraps an existing `src.search.criteria.FilterDefinition`
rather than re-implementing its comparison — `max_price`/`min_price`/`min_sqft` were
already correct, tested, and used by `ranking/ranking_engine.py`; duplicating their
logic here under a new name would be exactly the "no duplicated logic" violation
this sprint's non-functional requirements forbid.
"""

from __future__ import annotations

from typing import Any

from src.filter_engine.base_filter import BaseFilter, FilterContext
from src.filter_engine.metadata import FilterMetadata
from src.filter_engine.registry import register_filter
from src.search import criteria as legacy_criteria
from src.storage import apartment_repository
from src.storage.models import Apartment


class _LegacyCriteriaFilter(BaseFilter):
    """Delegates `validate()`/`apply()` to an existing, already-tested
    `search.criteria.FilterDefinition` — see module docstring.
    """

    _legacy_key: str

    def validate(self, value: Any) -> None:
        legacy_criteria.get_filter(self._legacy_key).validate(value)

    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        return legacy_criteria.get_filter(self._legacy_key).matches(apartment, value)


class MaxPriceFilter(_LegacyCriteriaFilter):
    key = "max_price"
    _legacy_key = "max_price"

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Maximum Price", category="price", value_type="number",
            description="Excludes apartments priced above the given amount (reuses search.criteria's max_price).",
        )


class MinPriceFilter(_LegacyCriteriaFilter):
    key = "min_price"
    _legacy_key = "min_price"

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Minimum Price", category="price", value_type="number",
            description="Excludes apartments priced below the given amount (reuses search.criteria's min_price).",
        )


class MinimumAreaFilter(_LegacyCriteriaFilter):
    key = "minimum_area"
    _legacy_key = "min_sqft"

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Minimum Area", category="property", value_type="number",
            description="Excludes apartments smaller than the given square footage (reuses search.criteria's min_sqft).",
        )


class MaximumAreaFilter(BaseFilter):
    key = "maximum_area"

    def validate(self, value: Any) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"expected a non-negative number, got {value!r}")

    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        if apartment.sqft is None:
            return False  # can't confirm "at or under the max" without a known area
        return apartment.sqft <= value

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Maximum Area", category="property", value_type="number",
            description="Excludes apartments larger than the given square footage. No legacy equivalent existed.",
        )


class NumberOfRoomsFilter(BaseFilter):
    """Exact bedroom count — distinct from `search.criteria`'s `min_bedrooms`
    (a minimum threshold); this is a precise match, e.g. "exactly 2 bedrooms."
    """

    key = "number_of_rooms"

    def validate(self, value: Any) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"expected a non-negative number, got {value!r}")

    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        if apartment.bedrooms is None:
            return False
        return apartment.bedrooms == value

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Number of Rooms", category="property", value_type="number",
            description="Exact bedroom count match (distinct from the pre-existing min_bedrooms threshold filter).",
        )


class CurrencyFilter(BaseFilter):
    key = "currency"

    def validate(self, value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"expected a non-empty currency code, got {value!r}")

    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        if apartment.currency is None:
            return False  # unknown currency can't be confirmed to match a specific one
        return apartment.currency.upper() == value.upper()

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Currency", category="price", value_type="string",
            description="Matches apartments priced in the given ISO currency code (e.g. USD). Populated by RentCast and (since v2.6) the demo connectors.",
        )


class PropertyTypeFilter(BaseFilter):
    key = "property_type"

    def validate(self, value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"expected a non-empty property type, got {value!r}")

    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        if apartment.property_type is None:
            return False
        return apartment.property_type.lower() == value.lower()

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Property Type", category="property", value_type="string",
            description="Matches apartments of the given property type (e.g. apartment, house, condo). Populated by RentCast and (since v2.6) the demo connectors.",
        )


class PlatformFilter(BaseFilter):
    """`value` is a single platform id or a list/set/tuple of them — matching any
    number of platforms without needing a separate "platforms" filter shape.
    """

    key = "platform"

    def validate(self, value: Any) -> None:
        values = value if isinstance(value, (list, tuple, set)) else [value]
        if not values or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f"expected a platform id or a list of platform ids, got {value!r}")

    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        values = value if isinstance(value, (list, tuple, set)) else [value]
        return apartment.platform_id in values

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Platform", category="platform", value_type="string",
            description="Matches apartments from the given platform id, or any of a list of platform ids.",
        )


class ImageCountFilter(BaseFilter):
    """Needs `context.conn` — image counts live in `apartment_images`, not on
    `Apartment` itself. Honestly reports "no evidence" (never excludes) when no
    connection is available, e.g. a caller using `FilterEngine` without a
    `FilterContext.conn` — the same graceful degradation the distance filters use
    when `analysis_results`/`conn` are both absent.
    """

    key = "image_count"

    def validate(self, value: Any) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"expected a non-negative number, got {value!r}")

    def apply(self, apartment: Apartment, value: Any, context: FilterContext) -> bool:
        if context.conn is None:
            return True
        images = apartment_repository.get_images(context.conn, apartment.id)
        return len([image for image in images if image.is_current]) >= value

    def metadata(self) -> FilterMetadata:
        return FilterMetadata(
            key=self.key, display_name="Minimum Image Count", category="media", value_type="number",
            description="Excludes apartments with fewer than the given number of current photos. Requires FilterContext.conn.",
        )


register_filter(MaxPriceFilter())
register_filter(MinPriceFilter())
register_filter(MinimumAreaFilter())
register_filter(MaximumAreaFilter())
register_filter(NumberOfRoomsFilter())
register_filter(CurrencyFilter())
register_filter(PropertyTypeFilter())
register_filter(PlatformFilter())
register_filter(ImageCountFilter())
