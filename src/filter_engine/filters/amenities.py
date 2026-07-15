"""14 dormant amenity filters — real, registered, tested `BaseFilter`s, each always
passing (see `dormant_base.py`) because no connector or schema field carries
amenity/utility flags yet. Three lines of configuration each, mirroring
`analysis/analyzers/nearby_amenity.py`'s own "shared base + minimal per-subclass
config" pattern for a large, structurally-identical family. See
docs/25_Dynamic_Filter_Engine.md "Dormant Filters" / "Built-In Filters".
"""

from __future__ import annotations

from src.filter_engine.filters.dormant_base import DORMANT_NOTE, DormantBooleanFilter
from src.filter_engine.metadata import FilterMetadata
from src.filter_engine.registry import register_filter


def _amenity_metadata(key: str, display_name: str) -> FilterMetadata:
    return FilterMetadata(
        key=key, display_name=display_name, category="amenities", value_type="boolean",
        is_dormant=True, description=f"{display_name}. {DORMANT_NOTE}",
    )


class PrivateBathroomFilter(DormantBooleanFilter):
    key = "private_bathroom"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Private Bathroom")


class PrivateKitchenFilter(DormantBooleanFilter):
    key = "private_kitchen"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Private Kitchen")


class AirConditioningFilter(DormantBooleanFilter):
    key = "air_conditioning"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Air Conditioning")


class HeatingFilter(DormantBooleanFilter):
    key = "heating"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Heating")


class BalconyFilter(DormantBooleanFilter):
    key = "balcony"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Balcony")


class TerraceFilter(DormantBooleanFilter):
    key = "terrace"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Terrace")


class ParkingFilter(DormantBooleanFilter):
    key = "parking"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Parking")


class ElevatorFilter(DormantBooleanFilter):
    key = "elevator"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Elevator")


class WheelchairAccessibleFilter(DormantBooleanFilter):
    key = "wheelchair_accessible"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Wheelchair Accessible")


class PetsAllowedFilter(DormantBooleanFilter):
    key = "pets_allowed"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Pets Allowed")


class SmokingAllowedFilter(DormantBooleanFilter):
    key = "smoking_allowed"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Smoking Allowed")


class InternetIncludedFilter(DormantBooleanFilter):
    key = "internet_included"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Internet Included")


class UtilitiesIncludedFilter(DormantBooleanFilter):
    key = "utilities_included"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Utilities Included")


class FurnishedFilter(DormantBooleanFilter):
    key = "furnished"

    def metadata(self) -> FilterMetadata:
        return _amenity_metadata(self.key, "Furnished")


register_filter(PrivateBathroomFilter())
register_filter(PrivateKitchenFilter())
register_filter(AirConditioningFilter())
register_filter(HeatingFilter())
register_filter(BalconyFilter())
register_filter(TerraceFilter())
register_filter(ParkingFilter())
register_filter(ElevatorFilter())
register_filter(WheelchairAccessibleFilter())
register_filter(PetsAllowedFilter())
register_filter(SmokingAllowedFilter())
register_filter(InternetIncludedFilter())
register_filter(UtilitiesIncludedFilter())
register_filter(FurnishedFilter())
