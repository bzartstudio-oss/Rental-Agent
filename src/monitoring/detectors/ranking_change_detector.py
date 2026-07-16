"""`RankingChangeDetector` — rank/score movement between two monitoring runs'
persisted `search_results`, and `BETTER_MATCH_FOUND` when a new top result
clears the previous best by a configurable margin. See
docs/30_Continuous_Monitoring.md "Ranking Integration".
"""

from __future__ import annotations

from src.monitoring import significance
from src.monitoring.base_detector import EventDetector, MonitoringDetectionContext
from src.monitoring.deduplication import make_dedup_key
from src.monitoring.metadata import EventDetectorMetadata
from src.monitoring.models import MonitoringEvent, MonitoringEventType
from src.monitoring.registry import register_event_detector


class RankingChangeDetector(EventDetector):
    detector_id = "ranking_change"

    def metadata(self) -> EventDetectorMetadata:
        return EventDetectorMetadata(
            detector_id=self.detector_id, display_name="Ranking Change Detector",
            description="Rank/score movement between runs, using each run's persisted search_results directly.",
            event_types=(MonitoringEventType.RANK_INCREASED, MonitoringEventType.RANK_DECREASED, MonitoringEventType.BETTER_MATCH_FOUND),
        )

    def detect(self, context: MonitoringDetectionContext) -> list[MonitoringEvent]:
        if not context.previous_search_results:
            return []

        events: list[MonitoringEvent] = []
        policy = context.version.monitoring_policy
        previous_by_id = {r.apartment_id: r for r in context.previous_search_results}
        current_by_id = {r.apartment_id: r for r in context.current_search_results}
        total_candidates = max(len(current_by_id), len(previous_by_id), 1)

        for apartment_id, current in current_by_id.items():
            previous = previous_by_id.get(apartment_id)
            if previous is None:
                continue
            rank_delta = previous.rank - current.rank  # positive = moved up (better)
            if rank_delta == 0:
                continue
            sig = significance.rank_change_significance(rank_delta, total_candidates)
            if abs(rank_delta) < policy.rank_change_significance_threshold:
                continue
            event_type = MonitoringEventType.RANK_INCREASED if rank_delta > 0 else MonitoringEventType.RANK_DECREASED
            dedup_key = make_dedup_key(context.saved_search.saved_search_id, apartment_id, event_type)
            new_value = {"rank": current.rank, "score": current.score}
            events.append(
                MonitoringEvent(
                    saved_search_id=context.saved_search.saved_search_id, saved_search_version=context.version.version,
                    monitoring_run_id=context.run.monitoring_run_id, search_id=context.run.search_id,
                    apartment_id=apartment_id, event_type=event_type,
                    severity=significance.severity_for_significance(sig), significance=sig,
                    old_value={"rank": previous.rank, "score": previous.score}, new_value=new_value,
                    explanation=f"Rank moved from #{previous.rank} to #{current.rank}",
                    evidence={"rank_delta": rank_delta}, detected_at=context.now, dedup_key=dedup_key,
                )
            )

        better_match = self._better_match_event(context, previous_by_id, current_by_id, policy)
        if better_match is not None:
            events.append(better_match)

        return events

    def _better_match_event(self, context, previous_by_id, current_by_id, policy) -> MonitoringEvent | None:
        current_top = next((r for r in context.current_search_results if r.rank == 1), None)
        previous_top = next((r for r in context.previous_search_results if r.rank == 1), None)
        if current_top is None or previous_top is None:
            return None
        if current_top.apartment_id == previous_top.apartment_id:
            return None  # same top result — no new "better match"

        score_delta = current_top.score - previous_top.score
        if score_delta <= policy.better_match_score_threshold:
            return None

        sig = significance.better_match_significance(score_delta, policy.better_match_score_threshold)
        dedup_key = make_dedup_key(context.saved_search.saved_search_id, current_top.apartment_id, MonitoringEventType.BETTER_MATCH_FOUND)
        new_value = {"apartment_id": current_top.apartment_id, "score": current_top.score}
        return MonitoringEvent(
            saved_search_id=context.saved_search.saved_search_id, saved_search_version=context.version.version,
            monitoring_run_id=context.run.monitoring_run_id, search_id=context.run.search_id,
            apartment_id=current_top.apartment_id, event_type=MonitoringEventType.BETTER_MATCH_FOUND,
            severity=significance.severity_for_significance(sig), significance=sig,
            old_value={"apartment_id": previous_top.apartment_id, "score": previous_top.score}, new_value=new_value,
            explanation=f"New top match exceeds previous best by {score_delta:.1f} points",
            evidence={"score_delta": score_delta, "threshold": policy.better_match_score_threshold},
            detected_at=context.now, dedup_key=dedup_key,
        )


register_event_detector(RankingChangeDetector())
