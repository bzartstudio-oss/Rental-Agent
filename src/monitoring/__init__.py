"""The Continuous Monitoring & Saved Search Engine — a modular, provider-
independent system that re-runs saved searches over time, compares runs, and
generates structured monitoring events. See docs/30_Continuous_Monitoring.md.

Importing this package imports `monitoring.detectors`, which is what runs
every built-in event detector's `register_event_detector(...)` call. Public
API re-exported here so callers don't need to know this package's internal
file layout — mirrors `src.discovery.automatic`'s own re-export shape.
"""

from __future__ import annotations

from src.monitoring import detectors as _detectors  # noqa: F401 — self-registration side effect
from src.monitoring.base_detector import EventDetector, MonitoringDetectionContext
from src.monitoring.engine import MonitoringEngine
from src.monitoring.exceptions import (
    MonitoringConfigurationError,
    MonitoringException,
    MonitoringRunClaimError,
    MonitoringValidationError,
)
from src.monitoring.metadata import EventDetectorMetadata
from src.monitoring.models import (
    MonitoringComparison,
    MonitoringConfiguration,
    MonitoringEvent,
    MonitoringEventType,
    MonitoringHealth,
    MonitoringPolicy,
    MonitoringReport,
    MonitoringRun,
    MonitoringRunStatus,
    MonitoringSchedule,
    MonitoringStatistics,
    RankChange,
    SavedSearch,
    SavedSearchVersion,
)
from src.monitoring.registry import MonitoringRegistry, register_event_detector

__all__ = [
    "EventDetector",
    "MonitoringDetectionContext",
    "MonitoringEngine",
    "MonitoringException",
    "MonitoringConfigurationError",
    "MonitoringRunClaimError",
    "MonitoringValidationError",
    "EventDetectorMetadata",
    "MonitoringComparison",
    "MonitoringConfiguration",
    "MonitoringEvent",
    "MonitoringEventType",
    "MonitoringHealth",
    "MonitoringPolicy",
    "MonitoringReport",
    "MonitoringRun",
    "MonitoringRunStatus",
    "MonitoringSchedule",
    "MonitoringStatistics",
    "RankChange",
    "SavedSearch",
    "SavedSearchVersion",
    "MonitoringRegistry",
    "register_event_detector",
]
