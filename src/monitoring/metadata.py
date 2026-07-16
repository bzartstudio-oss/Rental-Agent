"""`EventDetectorMetadata` — a detector's static self-description, mirroring
`DiscoveryProviderMetadata`/`GeoProviderMetadata`'s same declarative-capability
role.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EventDetectorMetadata:
    detector_id: str
    display_name: str
    description: str
    event_types: tuple[str, ...] = field(default_factory=tuple)
