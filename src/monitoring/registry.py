"""Where every installed event detector is known — mirrors
`DiscoveryProviderRegistry`'s self-registration + eager-import shape.
"""

from __future__ import annotations

from src.monitoring.base_detector import EventDetector
from src.monitoring.exceptions import MonitoringConfigurationError


class MonitoringRegistry:
    _detectors: dict[str, EventDetector] = {}

    @classmethod
    def register(cls, detector: EventDetector) -> EventDetector:
        if not isinstance(detector, EventDetector):
            raise MonitoringConfigurationError(
                f"{detector!r} is not an EventDetector instance — register_event_detector() "
                "must be called with an instantiated EventDetector subclass"
            )
        if not getattr(detector, "detector_id", None):
            raise MonitoringConfigurationError(
                f"{type(detector).__name__} must set a class-level `detector_id` before it can be registered"
            )
        cls._detectors[detector.detector_id] = detector
        return detector

    @classmethod
    def get(cls, detector_id: str) -> EventDetector:
        try:
            return cls._detectors[detector_id]
        except KeyError:
            raise MonitoringConfigurationError(
                f"No event detector registered for {detector_id!r}. Registered: {sorted(cls._detectors)}"
            ) from None

    @classmethod
    def all(cls) -> list[EventDetector]:
        return list(cls._detectors.values())

    @classmethod
    def is_registered(cls, detector_id: str) -> bool:
        return detector_id in cls._detectors

    @classmethod
    def reset(cls) -> None:
        """Test-only: clears every registered detector. Real code never calls this."""
        cls._detectors.clear()


def register_event_detector(detector: EventDetector) -> EventDetector:
    return MonitoringRegistry.register(detector)
