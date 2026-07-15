"""RawListing -> normalized fields ready to become an Apartment (storage/models.py).

Defensive cleanup that doesn't depend on which connector produced the raw data —
trimming, safe type coercion, and consistent defaults belong here once, not duplicated
in every connector. See docs/07_Analysis_Engine.md.
"""

from __future__ import annotations

from src.connectors.base import RawListing


def normalize(raw: RawListing) -> dict:
    """Returns a dict of fields matching storage.models.Apartment's constructor, minus
    id/platform_id/timestamps — the caller (analyzers/engine.py) assigns those based on
    whether this is a new apartment or a re-observation of one already known.
    """
    return {
        "platform_listing_id": raw.platform_listing_id.strip(),
        "title": raw.title.strip(),
        "current_price": max(0.0, float(raw.price)),
        "current_status": (raw.status or "available").strip().lower(),
        "url": raw.url.strip(),
        "bedrooms": raw.bedrooms,
        "bathrooms": raw.bathrooms,
        "sqft": raw.sqft,
        "address_raw": raw.address_raw.strip() if raw.address_raw else None,
        # v2.0 — required to exist before its changes can be tracked (docs/03_Data_Model.md).
        "description": raw.description.strip() if raw.description else None,
    }
