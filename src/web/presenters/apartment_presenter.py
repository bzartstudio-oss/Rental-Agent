"""Apartment card/detail presentation — see docs/32_Web_Dashboard.md "Results
Page"/"Apartment Detail Page".

"Never hide missing data by inventing values. Clearly label: confirmed
values, estimated values, inferred values, unavailable values" (the mission's
own words) — every field below carries one of those four labels rather than
silently omitting or guessing a value `Apartment`/`GeoEnrichment`/
`RankedApartmentV2` doesn't actually have.
"""

from __future__ import annotations

from src.geography.models import TravelMode


def present_apartment_card(apartment, *, geo_enrichment=None, ranking_v2=None, platform=None, connector_health=None) -> dict:
    walking = None
    transit = None
    if geo_enrichment is not None:
        walking_result = geo_enrichment.distances.get(TravelMode.WALKING)
        transit_result = geo_enrichment.distances.get(TravelMode.PUBLIC_TRANSPORT)
        walking = walking_result.travel_time_minutes if walking_result else None
        transit = transit_result.travel_time_minutes if transit_result else None

    reliability = connector_health.success_count / connector_health.observation_count if (
        connector_health and connector_health.observation_count
    ) else None

    return {
        "apartment_id": apartment.id,
        "title": {"value": apartment.title, "label": "confirmed"},
        "main_image": None,  # filled in by the caller from ApartmentImage rows (position 0, is_current)
        "price": {"value": apartment.current_price, "label": "confirmed"},
        "currency": {"value": apartment.currency, "label": "confirmed" if apartment.currency else "unavailable"},
        "property_type": {"value": apartment.property_type, "label": "confirmed" if apartment.property_type else "unavailable"},
        "room_type": {"value": None, "label": "unavailable"},  # not a field this platform's data model captures yet
        "location": {"value": apartment.address_raw, "label": "confirmed" if apartment.address_raw else "unavailable"},
        "availability": {"value": apartment.current_status, "label": "confirmed"},
        "score": {"value": ranking_v2["final_score"] if ranking_v2 else None, "label": "inferred" if ranking_v2 else "unavailable"},
        "confidence": {"value": ranking_v2["confidence"] if ranking_v2 else None, "label": "inferred" if ranking_v2 else "unavailable"},
        "top_positive_factors": ranking_v2["top_positive_factors"] if ranking_v2 else [],
        "top_negative_factors": ranking_v2["top_negative_factors"] if ranking_v2 else [],
        "walking_minutes": {"value": walking, "label": "estimated" if walking is not None else "unavailable"},
        "transit_minutes": {"value": transit, "label": "estimated" if transit is not None else "unavailable"},
        "nearby_count": sum(len(places) for places in geo_enrichment.nearby.values()) if geo_enrichment else 0,
        "platform_name": platform.name if platform else apartment.platform_id,
        "platform_reliability": {"value": reliability, "label": "estimated" if reliability is not None else "unavailable"},
        "last_seen_at": apartment.last_seen_at,
        "original_url": apartment.url,
    }


def present_missing_data_summary(apartment) -> list[str]:
    """A short, honest list of what's *not* known about this apartment —
    "Clearly label ... unavailable values" applied as a single glanceable
    list rather than scattered per-field.
    """
    missing = []
    if apartment.bedrooms is None:
        missing.append("bedrooms")
    if apartment.bathrooms is None:
        missing.append("bathrooms")
    if apartment.sqft is None:
        missing.append("area (sqft)")
    if apartment.currency is None:
        missing.append("currency")
    if apartment.property_type is None:
        missing.append("property type")
    if apartment.latitude is None or apartment.longitude is None:
        missing.append("coordinates (blocks geographic analysis)")
    return missing
