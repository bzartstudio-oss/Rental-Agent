from dataclasses import dataclass, field


@dataclass
class SearchSettings:
    country: str
    city: str
    radius_km: int
    currency: str
    max_price: int
    property_types: list[str]
    websites: list[str]


@dataclass
class DestinationSettings:
    address: str
    maximum_walk_minutes: int


@dataclass
class PreferenceSettings:
    air_conditioning: bool
    parking: bool
    balcony: bool
    pets_allowed: bool


@dataclass
class ReportSettings:
    generate_html: bool
    generate_pdf: bool


@dataclass
class Configuration:
    project_name: str
    version: str

    search: SearchSettings
    destination: DestinationSettings
    preferences: PreferenceSettings
    reports: ReportSettings