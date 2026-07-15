"""The remaining 13 dormant filters: preference flags (gender/student/professional),
structured geography (country/region/city — only `Apartment.address_raw` free text
exists today), stay duration/availability date, room type, flatmate count, and
radius (needs a search-center coordinate concept `SearchRequest` doesn't have yet).
See docs/25_Dynamic_Filter_Engine.md "Dormant Filters" / "Built-In Filters" and
`dormant_base.py` for why every one of these always passes.
"""

from __future__ import annotations

from src.filter_engine.filters.dormant_base import (
    DORMANT_NOTE,
    DormantBooleanFilter,
    DormantDateFilter,
    DormantNumberFilter,
    DormantStringFilter,
)
from src.filter_engine.metadata import FilterMetadata
from src.filter_engine.registry import register_filter


def _meta(key: str, display_name: str, category: str, value_type: str) -> FilterMetadata:
    return FilterMetadata(
        key=key, display_name=display_name, category=category, value_type=value_type,
        is_dormant=True, description=f"{display_name}. {DORMANT_NOTE}",
    )


# --- Preferences (room/flatshare concepts — see module docstring) ---------------

class GenderPreferenceFilter(DormantStringFilter):
    key = "gender_preference"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Gender Preference", "preferences", "string")


class StudentFriendlyFilter(DormantBooleanFilter):
    key = "student_friendly"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Student Friendly", "preferences", "boolean")


class ProfessionalFriendlyFilter(DormantBooleanFilter):
    key = "professional_friendly"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Professional Friendly", "preferences", "boolean")


# --- Structured geography (only address_raw free text exists today) ------------

class CountryFilter(DormantStringFilter):
    key = "country"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Country", "location", "string")


class RegionFilter(DormantStringFilter):
    key = "region"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Region", "location", "string")


class CityFilter(DormantStringFilter):
    key = "city"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "City", "location", "string")


class RadiusFilter(DormantNumberFilter):
    """Needs a search-center coordinate — `SearchRequest.location` is still a
    free-text string (docs/04_Search_Request.md's open question), so there is no
    coordinate to measure a radius *from* yet, independent of whether an apartment
    has its own coordinates.
    """

    key = "radius"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Radius", "location", "number")


# --- Stay duration / availability -----------------------------------------------

class AvailabilityDateFilter(DormantDateFilter):
    key = "availability_date"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Availability Date", "availability", "date")


class MinimumStayFilter(DormantNumberFilter):
    key = "minimum_stay"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Minimum Stay", "availability", "number")


class MaximumStayFilter(DormantNumberFilter):
    key = "maximum_stay"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Maximum Stay", "availability", "number")


# --- Room concept / language -----------------------------------------------------

class RoomTypeFilter(DormantStringFilter):
    """The SDK Validation Sprint's own Finding 1 (docs/22): `room_type` was requested
    by an earlier mission but never added to `RawListing`/`Apartment` — this filter
    makes that gap concrete and queryable rather than silently absent.
    """

    key = "room_type"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Room Type", "property", "string")


class NumberOfFlatmatesFilter(DormantNumberFilter):
    key = "number_of_flatmates"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Number of Flatmates", "property", "number")


class LanguageFilter(DormantStringFilter):
    key = "language"

    def metadata(self) -> FilterMetadata:
        return _meta(self.key, "Language", "platform", "string")


register_filter(GenderPreferenceFilter())
register_filter(StudentFriendlyFilter())
register_filter(ProfessionalFriendlyFilter())
register_filter(CountryFilter())
register_filter(RegionFilter())
register_filter(CityFilter())
register_filter(RadiusFilter())
register_filter(AvailabilityDateFilter())
register_filter(MinimumStayFilter())
register_filter(MaximumStayFilter())
register_filter(RoomTypeFilter())
register_filter(NumberOfFlatmatesFilter())
register_filter(LanguageFilter())
