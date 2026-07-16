"""`DiscoveryDetector` — surfaces newly-discovered platforms and connector-
availability changes found by an optional platform-discovery refresh this
cycle. Reuses `DiscoveryComparison` (Step 13's Automatic Platform Discovery
Agent) directly. A no-op whenever `context.discovery_comparison` is `None`
(discovery refresh wasn't requested this run — "Do not rerun discovery unless
policy requires it," the mission's own words).
"""

from __future__ import annotations

from src.monitoring import significance
from src.monitoring.base_detector import EventDetector, MonitoringDetectionContext
from src.monitoring.deduplication import make_dedup_key
from src.monitoring.metadata import EventDetectorMetadata
from src.monitoring.models import MonitoringEvent, MonitoringEventType
from src.monitoring.registry import register_event_detector


class DiscoveryDetector(EventDetector):
    detector_id = "discovery"

    def metadata(self) -> EventDetectorMetadata:
        return EventDetectorMetadata(
            detector_id=self.detector_id, display_name="Discovery Detector",
            description="New platform candidates and connector-availability changes found by an optional discovery refresh.",
            event_types=(
                MonitoringEventType.DISCOVERY_FOUND_NEW_PLATFORM,
                MonitoringEventType.PLATFORM_BECAME_ACCESSIBLE,
            ),
        )

    def detect(self, context: MonitoringDetectionContext) -> list[MonitoringEvent]:
        comparison = context.discovery_comparison
        if comparison is None:
            return []

        events = []
        for candidate_id in comparison.new_candidate_ids:
            event = self._build(
                context, candidate_id, MonitoringEventType.DISCOVERY_FOUND_NEW_PLATFORM,
                significance.DISCOVERY_FOUND_NEW_PLATFORM, f"Discovery found a new platform candidate: {candidate_id}",
            )
            events.append(event)

        for candidate_id in comparison.changed_connector_availability_candidate_ids:
            event = self._build(
                context, candidate_id, MonitoringEventType.PLATFORM_BECAME_ACCESSIBLE,
                significance.PLATFORM_BECAME_ACCESSIBLE, f"Platform candidate connector availability changed: {candidate_id}",
            )
            events.append(event)

        return events

    def _build(self, context: MonitoringDetectionContext, subject_id: str, event_type: str, sig: float, explanation: str) -> MonitoringEvent:
        dedup_key = make_dedup_key(context.saved_search.saved_search_id, subject_id, event_type)
        new_value = {"candidate_id": subject_id}
        return MonitoringEvent(
            saved_search_id=context.saved_search.saved_search_id, saved_search_version=context.version.version,
            monitoring_run_id=context.run.monitoring_run_id, search_id=context.run.search_id,
            event_type=event_type, severity=significance.severity_for_significance(sig), significance=sig,
            new_value=new_value, explanation=explanation, evidence={"candidate_id": subject_id},
            detected_at=context.now, dedup_key=dedup_key,
        )


register_event_detector(DiscoveryDetector())
