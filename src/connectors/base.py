"""The contract every connector implements — see docs/06_Connector_Framework.md.

`RawListing` is the shared, pre-normalization output shape every connector returns,
regardless of platform. It's intentionally looser than storage.models.Apartment (no id,
no timestamps — those get assigned by the Analysis Engine when it decides whether this is
a new apartment or a re-observation of one already known).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
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


class Connector(ABC):
    """Every connector implementation must contain *only* platform-specific logic (URL
    structure, selectors/API shape, query building) and must fetch through a Collector
    (collectors/browser_collector.py or http_collector.py) rather than hand-rolling its
    own Playwright/HTTP calls — see docs/06_Connector_Framework.md and
    docs/01_System_Architecture.md "The Independence Guardrail".
    """

    platform_id: str

    @abstractmethod
    def search(self, criteria: dict) -> list[RawListing]:
        """Given normalized search criteria (derived from a SearchRequest), return this
        platform's raw results. Must not perform normalization — that's analyzers/'s job.
        """
        raise NotImplementedError
