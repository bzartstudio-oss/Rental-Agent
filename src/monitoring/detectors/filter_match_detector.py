"""`FilterMatchDetector` — an existing (not brand-new, not removed) apartment
gaining or losing a match against this saved search's active filters, derived
from the persisted `search_results` set for each run (an apartment surviving
to `search_results` means it passed both hard-filtering and ranking). See
docs/30_Continuous_Monitoring.md "Change Detection".
"""

from __future__ import annotations

from src.monitoring import significance
from src.monitoring.base_detector import EventDetector, MonitoringDetectionContext
from src.monitoring.deduplication import make_dedup_key
from src.monitoring.metadata import EventDetectorMetadata
from src.monitoring.models import MonitoringEvent, MonitoringEventType
from src.monitoring.registry import register_event_detector


class FilterMatchDetector(EventDetector):
    detector_id = "filter_match"

    def metadata(self) -> EventDetectorMetadata:
        return EventDetectorMetadata(
            detector_id=self.detector_id, display_name="Filter Match Detector",
            description="Existing apartments entering or leaving the saved search's active filters.",
            event_types=(MonitoringEventType.FILTER_MATCH_GAINED, MonitoringEventType.FILTER_MATCH_LOST),
        )

    def detect(self, context: MonitoringDetectionContext) -> list[MonitoringEvent]:
        comparison = context.search_comparison
        if comparison is None or not context.previous_search_results:
            return []

        current_ids = {r.apartment_id for r in context.current_search_results}
        previous_ids = {r.apartment_id for r in context.previous_search_results}
        new_ids = set(comparison.new_apartment_ids)
        removed_ids = set(comparison.removed_apartment_ids)

        gained = (current_ids - previous_ids) - new_ids
        lost = (previous_ids - current_ids) - removed_ids

        events = []
        for apartment_id in gained:
            event = self._build(context, apartment_id, MonitoringEventType.FILTER_MATCH_GAINED, "gained a match against this saved search's filters")
            events.append(event)
        for apartment_id in lost:
            event = self._build(context, apartment_id, MonitoringEventType.FILTER_MATCH_LOST, "no longer matches this saved search's filters")
            events.append(event)
        return events

    def _build(self, context: MonitoringDetectionContext, apartment_id: str, event_type: str, explanation_suffix: str) -> MonitoringEvent:
        sig = significance.FILTER_MATCH_GAINED if event_type == MonitoringEventType.FILTER_MATCH_GAINED else significance.FILTER_MATCH_LOST
        dedup_key = make_dedup_key(context.saved_search.saved_search_id, apartment_id, event_type)
        new_value = {"matches": event_type == MonitoringEventType.FILTER_MATCH_GAINED}
        return MonitoringEvent(
            saved_search_id=context.saved_search.saved_search_id, saved_search_version=context.version.version,
            monitoring_run_id=context.run.monitoring_run_id, search_id=context.run.search_id, apartment_id=apartment_id,
            event_type=event_type, severity=significance.severity_for_significance(sig), significance=sig,
            new_value=new_value, explanation=f"Apartment {explanation_suffix}",
            evidence={"apartment_id": apartment_id}, detected_at=context.now, dedup_key=dedup_key,
        )


register_event_detector(FilterMatchDetector())
