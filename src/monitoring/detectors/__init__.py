"""Importing this package runs every built-in event detector's
`register_event_detector(...)` call — mirrors
`src.discovery.automatic.providers`'s own self-registration-by-import shape.
"""

from __future__ import annotations

from src.monitoring.detectors import (  # noqa: F401
    apartment_change_detector,
    discovery_detector,
    filter_match_detector,
    platform_health_detector,
    ranking_change_detector,
)

__all__: list[str] = []
