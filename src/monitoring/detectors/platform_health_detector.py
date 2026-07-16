"""`PlatformHealthDetector` — connector failure/recovery between this run and
the previous one, from each `MonitoringRun`'s own `platforms_failed` list
(already the result of the same per-platform failure isolation
`RentalResearchAgent.run()` provides). See
docs/30_Continuous_Monitoring.md "Failure Isolation".
"""

from __future__ import annotations

from src.monitoring import significance
from src.monitoring.base_detector import EventDetector, MonitoringDetectionContext
from src.monitoring.deduplication import make_dedup_key
from src.monitoring.metadata import EventDetectorMetadata
from src.monitoring.models import MonitoringEvent, MonitoringEventType
from src.monitoring.registry import register_event_detector


class PlatformHealthDetector(EventDetector):
    detector_id = "platform_health"

    def metadata(self) -> EventDetectorMetadata:
        return EventDetectorMetadata(
            detector_id=self.detector_id, display_name="Platform Health Detector",
            description="Connector failure/recovery between consecutive monitoring runs.",
            event_types=(MonitoringEventType.CONNECTOR_FAILURE, MonitoringEventType.CONNECTOR_RECOVERED),
        )

    def detect(self, context: MonitoringDetectionContext) -> list[MonitoringEvent]:
        previous_failed = set(context.previous_run.platforms_failed) if context.previous_run is not None else set()
        current_failed = set(context.run.platforms_failed)

        newly_failed = current_failed - previous_failed
        recovered = previous_failed - current_failed

        events = []
        for platform_id in newly_failed:
            event = self._build(context, platform_id, MonitoringEventType.CONNECTOR_FAILURE, significance.CONNECTOR_FAILURE, "started failing")
            events.append(event)
        for platform_id in recovered:
            event = self._build(context, platform_id, MonitoringEventType.CONNECTOR_RECOVERED, significance.CONNECTOR_RECOVERED, "recovered")
            events.append(event)
        return events

    def _build(self, context: MonitoringDetectionContext, platform_id: str, event_type: str, sig: float, verb: str) -> MonitoringEvent:
        dedup_key = make_dedup_key(context.saved_search.saved_search_id, platform_id, event_type)
        new_value = {"platform_id": platform_id}
        return MonitoringEvent(
            saved_search_id=context.saved_search.saved_search_id, saved_search_version=context.version.version,
            monitoring_run_id=context.run.monitoring_run_id, search_id=context.run.search_id, platform_id=platform_id,
            event_type=event_type, severity=significance.severity_for_significance(sig), significance=sig,
            new_value=new_value, explanation=f"Platform {platform_id} {verb}",
            evidence={"platform_id": platform_id}, detected_at=context.now, dedup_key=dedup_key,
        )


register_event_detector(PlatformHealthDetector())
