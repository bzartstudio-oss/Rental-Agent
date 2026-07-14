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
    status: str = "available"
    image_urls: list[str] = field(default_factory=list)


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
