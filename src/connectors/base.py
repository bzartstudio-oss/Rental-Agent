"""`RawListing` — the shared, pre-normalization output shape every connector returns,
regardless of platform or source format. It's intentionally looser than
storage.models.Apartment (no id, no timestamps — those get assigned by the Analysis
Engine when it decides whether this is a new apartment or a re-observation of one
already known).

The `Connector` abstract base class that used to live in this module (v1.0/v1.1) was
replaced in v2.0 Step 5 by `src.connectors.sdk.BaseConnector` — a template method with
a full lifecycle (connect/fetch/parse/normalize/validate/health-check), not a single
abstract `search()` method. See docs/18_Connector_SDK.md. `RawListing` itself is
unaffected and stays here: it's imported widely (analyzers/, knowledge/, the SDK
itself) and nothing about its shape changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawListing:
    platform_listing_id: str
    title: str
    price: float
    url: str
    bedrooms: float | None = None
    bathrooms: float | None = None
    sqft: float | None = None
    address_raw: str | None = None
    # v2.0 Step 4 — was `str = "available"`. That default made a connector that never
    # sets status indistinguishable from one that explicitly reports "available" (both
    # produce the same value), which is exactly what
    # docs/16_Knowledge_Engine.md's availability_quality_score needs to detect. The
    # actual "default to available" behavior moves to normalizer.py (`raw.status or
    # "available"`), which already existed and needed no change.
    status: str | None = None
    image_urls: list[str] = field(default_factory=list)
    # v2.0 (migration 0001) — populated only if the platform provides one; None is a
    # real, honest "no description available" rather than a missing-field bug. See
    # docs/03_Data_Model.md `apartments.description` and docs/07_Analysis_Engine.md.
    description: str | None = None
