"""`WebServiceFacade` — the one thing every HTML route and every JSON API
endpoint calls into. See docs/32_Web_Dashboard.md "Service Facade".

Every method here either (a) delegates straight to an existing engine/service
function, or (b) does pure read-aggregation/translation for display. No
method computes a ranking score, applies a filter, evaluates monitoring
significance, or decides notification eligibility itself — those decisions
live exactly where every prior sprint already put them. This mirrors
`MonitoringEngine`'s own docstring: "Every heavy engine is reused exactly as
published — this module only adds orchestration ... on top," applied one
layer higher, for the web boundary instead of the monitoring boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.discovery import platform_registry
from src.discovery.automatic import service as discovery_service
from src.discovery.automatic.models import PlatformEvidence, PlatformStatus
from src.discovery.discovery_agent import DiscoveryAgent
from src.discovery.discovery_agent import PlatformCandidate as SyncPlatformCandidate
from src.feedback.models import FeedbackEvent, FeedbackMode
from src.feedback import service as feedback_service
from src.filter_engine.registry import FilterRegistry
from src.geography.history import get_geo_history_for_apartment
from src.knowledge import knowledge_service
from src.monitoring import service as monitoring_service
from src.monitoring.models import MonitoringPolicy
from src.notifications import service as notification_service
from src.notifications.registry import NotificationChannelRegistry
from src.ranking_v2.profile import RankingProfile
from src.ranking_v2.weights import RankingWeights
from src.storage import (
    apartment_history_repository,
    apartment_repository,
    search_memory_repository,
    search_repository,
    web_repository,
)
from src.storage.models import WebRecentViewRecord, WebSavedComparisonRecord
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.dependencies import WebDependencies
from src.web.error_handler import WebNotFoundError, WebValidationError
from src.web.health import WebHealth
from src.web.jobs import service as jobs_service
from src.web.jobs.models import Job
from src.web.statistics import WebStatistics


class WebServiceFacade:
    def __init__(self, dependencies: WebDependencies) -> None:
        self._deps = dependencies
        self._db = dependencies.db

    # ------------------------------------------------------------------ #
    # dashboard
    # ------------------------------------------------------------------ #

    def dashboard_snapshot(self, profile_id: str = DEFAULT_PROFILE_ID) -> dict:
        with self._db.transaction() as conn:
            recent_jobs = jobs_service.list_recent_jobs(conn, profile_id=profile_id, limit=8)
            saved_searches = monitoring_service.get_all_saved_searches(conn)
            unacknowledged_events = monitoring_service.get_unacknowledged_events(conn)[:10]
            unacknowledged_deliveries = notification_service.get_unacknowledged_deliveries(conn)[:10]
            recent_candidates = sorted(
                discovery_service.get_all_candidates(conn), key=lambda c: c.first_discovered_at, reverse=True,
            )[:5]
            recent_search_ids = [
                row["id"] for row in conn.execute(
                    "SELECT id FROM search_requests ORDER BY created_at DESC LIMIT 5"
                ).fetchall()
            ]
            top_apartments = []
            for search_id in recent_search_ids[:1]:
                for entry in sorted(search_repository.get_search_results(conn, search_id), key=lambda e: e.rank)[:5]:
                    apartment = apartment_repository.get_apartment(conn, entry.apartment_id)
                    if apartment is not None:
                        top_apartments.append((entry, apartment))
            connector_health = knowledge_service.connector_health(conn)
            statistics = WebStatistics.collect(conn, self._deps.configuration.data_dir / "rental_intelligence.db")

        next_run_at = None
        for saved_search in saved_searches:
            schedule = None
            with self._db.transaction() as conn:
                schedule = monitoring_service.get_schedule(conn, saved_search.saved_search_id)
            if schedule and schedule.next_run_at and (next_run_at is None or schedule.next_run_at < next_run_at):
                next_run_at = schedule.next_run_at

        return {
            "recent_jobs": recent_jobs,
            "saved_searches": saved_searches,
            "unacknowledged_events": unacknowledged_events,
            "unacknowledged_deliveries": unacknowledged_deliveries,
            "recent_candidates": recent_candidates,
            "top_apartments": top_apartments,
            "connector_health": connector_health,
            "statistics": statistics,
            "next_run_at": next_run_at,
        }

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #

    def available_filters(self) -> list:
        return sorted((f.metadata() for f in FilterRegistry.all()), key=lambda m: (m.category, m.display_name))

    def start_search(self, *, profile_id: str, location: str, criteria: dict, label: str | None,
                      use_filter_engine: bool, use_geo_engine: bool, ranking_weights: dict | None,
                      feedback_mode: str | None, allowed_platform_ids: list[str] | None) -> Job:
        if not location or not location.strip():
            raise WebValidationError("Location is required")
        ranking_profile = None
        if ranking_weights:
            ranking_profile = RankingProfile(name="web_custom", description="Custom weights chosen in the web dashboard",
                                              weights=RankingWeights(values=ranking_weights))
        else:
            from src.ranking_v2 import DEFAULT_PROFILE
            ranking_profile = DEFAULT_PROFILE
        mode = FeedbackMode(feedback_mode) if feedback_mode else None
        return self._deps.job_runner.start_search_job(
            profile_id=profile_id, location=location, criteria=criteria, label=label,
            use_filter_engine=use_filter_engine, use_geo_engine=use_geo_engine, ranking_profile=ranking_profile,
            feedback_mode=mode, allowed_platform_ids=allowed_platform_ids,
        )

    def get_job(self, job_id: str) -> Job:
        with self._db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
        if job is None:
            raise WebNotFoundError(f"No such job {job_id!r}")
        return job

    def request_job_cancellation(self, job_id: str) -> Job:
        with self._db.transaction() as conn:
            job = jobs_service.request_cancellation(conn, job_id)
        if job is None:
            raise WebNotFoundError(f"No such job {job_id!r}")
        return job

    def recent_jobs(self, profile_id: str = DEFAULT_PROFILE_ID, limit: int = 20) -> list[Job]:
        with self._db.transaction() as conn:
            return jobs_service.list_recent_jobs(conn, profile_id=profile_id, limit=limit)

    def search_results(self, search_id: str) -> dict:
        with self._db.transaction() as conn:
            request_record = search_repository.get_search_request(conn, search_id)
            if request_record is None:
                raise WebNotFoundError(f"No such search {search_id!r}")
            entries = sorted(search_repository.get_search_results(conn, search_id), key=lambda e: e.rank)
            apartments = {}
            analysis = {}
            for entry in entries:
                apartment = apartment_repository.get_apartment(conn, entry.apartment_id)
                if apartment is not None:
                    apartments[entry.apartment_id] = apartment
                from src.analysis import analysis_service
                latest = analysis_service.latest_analysis(conn, entry.apartment_id)
                if latest is not None:
                    analysis[entry.apartment_id] = latest
        job = self._find_job_for_search(search_id)
        ranking_v2 = (job.metadata.get("ranking_v2") if job else None) or {}
        return {
            "request": request_record, "entries": entries, "apartments": apartments,
            "analysis": analysis, "ranking_v2": ranking_v2, "job": job,
        }

    def _find_job_for_search(self, search_id: str) -> Job | None:
        with self._db.transaction() as conn:
            for job in jobs_service.list_recent_jobs(conn, limit=200):
                if job.result_reference == search_id:
                    return job
        return None

    # ------------------------------------------------------------------ #
    # apartments
    # ------------------------------------------------------------------ #

    def apartment_detail(self, apartment_id: str, *, search_id: str | None = None, profile_id: str = DEFAULT_PROFILE_ID) -> dict:
        with self._db.transaction() as conn:
            apartment = apartment_repository.get_apartment(conn, apartment_id)
            if apartment is None:
                raise WebNotFoundError(f"No such apartment {apartment_id!r}")
            images = apartment_repository.get_images(conn, apartment_id)
            price_history = apartment_repository.get_price_history(conn, apartment_id)
            availability_history = apartment_repository.get_availability_history(conn, apartment_id)
            change_log = apartment_history_repository.get_change_log(conn, apartment_id)
            image_events = apartment_history_repository.get_image_events(conn, apartment_id)
            geo_history = get_geo_history_for_apartment(conn, apartment_id)
            from src.analysis import analysis_service
            analysis_history = analysis_service.analysis_history(conn, apartment_id)
            platform = platform_registry.get_platform(conn, apartment.platform_id)
            connector_health = [h for h in knowledge_service.connector_health(conn) if h.platform_id == apartment.platform_id]
            feedback_events = feedback_service.get_events_for_apartment(conn, apartment_id)
            web_repository.record_recent_view(
                conn, WebRecentViewRecord(profile_id=profile_id, apartment_id=apartment_id, viewed_at=datetime.now(timezone.utc)),
            )

        ranking_v2_entry = None
        if search_id:
            job = self._find_job_for_search(search_id)
            if job:
                ranking_v2_entry = (job.metadata.get("ranking_v2") or {}).get(apartment_id)

        return {
            "apartment": apartment, "images": images, "price_history": price_history,
            "availability_history": availability_history, "change_log": change_log, "image_events": image_events,
            "geo_history": geo_history, "analysis_history": analysis_history, "platform": platform,
            "connector_health": connector_health, "feedback_events": feedback_events,
            "ranking_v2": ranking_v2_entry, "search_id": search_id,
        }

    def recent_views(self, profile_id: str = DEFAULT_PROFILE_ID, limit: int = 10) -> list:
        with self._db.transaction() as conn:
            return web_repository.get_recent_views(conn, profile_id=profile_id, limit=limit)

    # ------------------------------------------------------------------ #
    # comparison
    # ------------------------------------------------------------------ #

    def save_comparison(self, apartment_ids: list[str], *, profile_id: str = DEFAULT_PROFILE_ID, name: str | None = None) -> str:
        if not (2 <= len(apartment_ids) <= 5):
            raise WebValidationError("A comparison requires between 2 and 5 apartments")
        comparison_id = str(uuid.uuid4())
        with self._db.transaction() as conn:
            for apartment_id in apartment_ids:
                if apartment_repository.get_apartment(conn, apartment_id) is None:
                    raise WebValidationError(f"No such apartment {apartment_id!r}")
            web_repository.add_saved_comparison(
                conn, WebSavedComparisonRecord(comparison_id=comparison_id, profile_id=profile_id, name=name,
                                                apartment_ids=apartment_ids, created_at=datetime.now(timezone.utc)),
            )
        return comparison_id

    def comparison_apartments(self, apartment_ids: list[str]) -> list:
        with self._db.transaction() as conn:
            apartments = []
            for apartment_id in apartment_ids:
                apartment = apartment_repository.get_apartment(conn, apartment_id)
                if apartment is None:
                    continue
                from src.analysis import analysis_service
                analysis = analysis_service.latest_analysis(conn, apartment_id)
                geo_history = get_geo_history_for_apartment(conn, apartment_id)
                platform = platform_registry.get_platform(conn, apartment.platform_id)
                apartments.append({"apartment": apartment, "analysis": analysis, "geo_history": geo_history, "platform": platform})
        return apartments

    def get_saved_comparison(self, comparison_id: str):
        with self._db.transaction() as conn:
            record = web_repository.get_saved_comparison(conn, comparison_id)
        if record is None:
            raise WebNotFoundError(f"No such comparison {comparison_id!r}")
        return record

    # ------------------------------------------------------------------ #
    # saved searches / monitoring
    # ------------------------------------------------------------------ #

    def create_saved_search(self, *, name: str, location: str, criteria: dict, profile_id: str = DEFAULT_PROFILE_ID,
                             description: str | None = None, enable_monitoring: bool = True,
                             geographic_destinations: list | None = None):
        if not name or not name.strip():
            raise WebValidationError("Saved search name is required")
        if not location or not location.strip():
            raise WebValidationError("Location is required")
        saved_search = self._deps.monitoring_engine.create_saved_search(
            self._db, name, {"location": location, "criteria": criteria}, profile_id=profile_id,
            description=description, monitoring_policy=MonitoringPolicy(),
            geographic_destinations=geographic_destinations,
        )
        if not enable_monitoring:
            self._deps.monitoring_engine.set_enabled(self._db, saved_search.saved_search_id, False)
        return saved_search

    def list_saved_searches(self, *, enabled_only: bool = False):
        with self._db.transaction() as conn:
            return monitoring_service.get_all_saved_searches(conn, enabled_only=enabled_only)

    def get_saved_search(self, saved_search_id: str):
        with self._db.transaction() as conn:
            saved_search = monitoring_service.get_saved_search(conn, saved_search_id)
            if saved_search is None:
                raise WebNotFoundError(f"No such saved search {saved_search_id!r}")
            versions = monitoring_service.get_saved_search_versions(conn, saved_search_id)
            runs = sorted(monitoring_service.get_runs_for_saved_search(conn, saved_search_id), key=lambda r: r.started_at, reverse=True)
            schedule = monitoring_service.get_schedule(conn, saved_search_id)
        return {"saved_search": saved_search, "versions": versions, "runs": runs, "schedule": schedule}

    def update_saved_search(self, saved_search_id: str, **overrides):
        return self._deps.monitoring_engine.update_saved_search(self._db, saved_search_id, **overrides)

    def set_monitoring_enabled(self, saved_search_id: str, enabled: bool):
        return self._deps.monitoring_engine.set_enabled(self._db, saved_search_id, enabled)

    def run_saved_search_now(self, saved_search_id: str, *, profile_id: str = DEFAULT_PROFILE_ID) -> Job:
        with self._db.transaction() as conn:
            if monitoring_service.get_saved_search(conn, saved_search_id) is None:
                raise WebNotFoundError(f"No such saved search {saved_search_id!r}")
        return self._deps.job_runner.start_monitoring_run_job(profile_id=profile_id, saved_search_id=saved_search_id)

    def compare_monitoring_runs(self, previous_run_id: str, current_run_id: str):
        from src.monitoring import statistics as monitoring_statistics

        with self._db.transaction() as conn:
            return monitoring_statistics.compare_monitoring_runs(conn, previous_run_id, current_run_id)

    def list_monitoring_events(self, *, saved_search_id: str | None = None, unacknowledged_only: bool = False):
        with self._db.transaction() as conn:
            if saved_search_id:
                events = monitoring_service.get_events_for_saved_search(conn, saved_search_id)
            else:
                events = monitoring_service.get_unacknowledged_events(conn) if unacknowledged_only else []
        return events

    def acknowledge_event(self, event_id: str, *, acknowledged_by: str | None = None, note: str | None = None):
        with self._db.transaction() as conn:
            monitoring_service.acknowledge_event(conn, event_id, acknowledged_by=acknowledged_by, note=note, now=datetime.now(timezone.utc))

    # ------------------------------------------------------------------ #
    # notifications
    # ------------------------------------------------------------------ #

    def create_notification_preference(self, *, profile_id: str, enabled_channels: list[str], **overrides):
        return self._deps.notification_engine.create_preference(self._db, profile_id, enabled_channels=enabled_channels, **overrides)

    def list_notification_preferences(self, *, profile_id: str | None = None):
        with self._db.transaction() as conn:
            return notification_service.get_all_preferences(conn, profile_id=profile_id)

    def get_notification_preference(self, preference_id: str):
        with self._db.transaction() as conn:
            preference = notification_service.get_preference(conn, preference_id)
            if preference is None:
                raise WebNotFoundError(f"No such notification preference {preference_id!r}")
            version = notification_service.get_latest_preference_version(conn, preference_id)
        return {"preference": preference, "version": version}

    def update_notification_preference(self, preference_id: str, **overrides):
        return self._deps.notification_engine.update_preference(self._db, preference_id, **overrides)

    def set_notification_enabled(self, preference_id: str, enabled: bool):
        return self._deps.notification_engine.set_enabled(self._db, preference_id, enabled)

    def preview_notification(self, preference_id: str, event_ids: list[str], channel_name: str) -> str:
        return self._deps.notification_engine.preview(self._db, preference_id, event_ids, channel_name)

    def channel_config_status(self) -> list:
        # `channel_info()` already redacts credentials — see
        # `notifications/base_channel.py`; never pass raw configuration here.
        return [channel.channel_info() for channel in NotificationChannelRegistry.all()]

    def deliver_pending_notifications(self):
        return self._deps.notification_engine.process_pending_deliveries(self._db)

    def retry_due_notifications(self):
        return self._deps.notification_engine.retry_due_failures(self._db)

    def generate_digest(self, preference_id: str):
        return self._deps.notification_engine.generate_digest(self._db, preference_id)

    def list_deliveries(self, *, profile_id: str | None = None, status: str | None = None):
        with self._db.transaction() as conn:
            if status:
                return notification_service.get_deliveries_by_status(conn, status)
            if profile_id:
                return notification_service.get_deliveries_for_profile(conn, profile_id)
            return notification_service.get_unacknowledged_deliveries(conn)

    def get_delivery(self, delivery_id: str):
        with self._db.transaction() as conn:
            delivery = notification_service.get_delivery(conn, delivery_id)
            if delivery is None:
                raise WebNotFoundError(f"No such notification delivery {delivery_id!r}")
            attempts = notification_service.get_attempts_for_delivery(conn, delivery_id)
            messages = notification_service.get_messages_for_delivery(conn, delivery_id)
            acknowledgements = notification_service.get_acknowledgements_for_delivery(conn, delivery_id)
        return {"delivery": delivery, "attempts": attempts, "messages": messages, "acknowledgements": acknowledgements}

    def acknowledge_delivery(self, delivery_id: str, *, acknowledged_by: str | None = None, note: str | None = None):
        return self._deps.notification_engine.acknowledge(self._db, delivery_id, acknowledged_by=acknowledged_by, note=note)

    def retry_delivery(self, delivery_id: str):
        return self._deps.notification_engine.retry_delivery_now(self._db, delivery_id)

    def cancel_delivery(self, delivery_id: str):
        return self._deps.notification_engine.cancel_delivery(self._db, delivery_id)

    # ------------------------------------------------------------------ #
    # discovery
    # ------------------------------------------------------------------ #

    def start_discovery_run(self, *, profile_id: str = DEFAULT_PROFILE_ID, country: str | None, region: str | None,
                             city: str | None, rental_categories: list[str] | None = None) -> Job:
        if not country and not city:
            raise WebValidationError("At least a country or a city is required for platform discovery")
        return self._deps.job_runner.start_discovery_run_job(
            profile_id=profile_id, country=country, region=region, city=city, rental_categories=rental_categories,
        )

    def list_candidates(self, *, status: str | None = None):
        with self._db.transaction() as conn:
            if status:
                return discovery_service.get_candidates_by_status(conn, status)
            return discovery_service.get_all_candidates(conn)

    def get_candidate(self, candidate_id: str):
        with self._db.transaction() as conn:
            candidate = discovery_service.get_candidate(conn, candidate_id)
            if candidate is None:
                raise WebNotFoundError(f"No such discovery candidate {candidate_id!r}")
            evidence = discovery_service.get_evidence_for_candidate(conn, candidate_id)
            verification = discovery_service.get_verification_results(conn, candidate_id)
            capabilities = discovery_service.get_capability_estimates(conn, candidate_id)
        return {"candidate": candidate, "evidence": evidence, "verification": verification, "capabilities": capabilities}

    def approve_candidate(self, candidate_id: str, *, connector_name: str | None = None):
        with self._db.transaction() as conn:
            candidate = discovery_service.get_candidate(conn, candidate_id)
        if candidate is None:
            raise WebNotFoundError(f"No such discovery candidate {candidate_id!r}")
        sync_candidate = SyncPlatformCandidate(
            platform_id=candidate.matched_platform_id or candidate.normalized_domain.replace(".", "_"),
            name=candidate.name, country=candidate.country or "unknown", homepage=candidate.raw_url,
            connector_available=candidate.status is PlatformStatus.CONNECTOR_AVAILABLE,
            connector_name=connector_name, discovery_method="automatic_discovery_approved",
            notes=f"Approved from discovery candidate {candidate.candidate_id} (classification={candidate.classification.value})",
        )
        return DiscoveryAgent(self._db).sync_platforms([sync_candidate])

    def reject_candidate(self, candidate_id: str, *, reason: str | None = None):
        with self._db.transaction() as conn:
            candidate = discovery_service.get_candidate(conn, candidate_id)
            if candidate is None:
                raise WebNotFoundError(f"No such discovery candidate {candidate_id!r}")
            candidate.status = PlatformStatus.UNSUPPORTED
            discovery_service.update_candidate(conn, candidate)
            discovery_service.record_evidence(
                conn, PlatformEvidence(
                    candidate_id=candidate.candidate_id, run_id=candidate.last_run_id,
                    evidence_type="manual_review_decision", discovery_provider="web_dashboard",
                    value={"decision": "rejected", "reason": reason}, collected_at=datetime.now(timezone.utc),
                ),
            )

    def list_platforms(self, *, connector_available_only: bool = False):
        with self._db.transaction() as conn:
            if connector_available_only:
                return platform_registry.list_connector_available_platforms(conn)
            return platform_registry.list_all_platforms(conn)

    def compare_discovery_runs(self, previous_run_id: str, current_run_id: str):
        return self._deps.discovery_agent.compare_discovery_runs(self._db.connect(), previous_run_id, current_run_id)

    def discovery_history(self):
        with self._db.transaction() as conn:
            return self._deps.discovery_agent.discovery_history(conn)

    def discovery_coverage_summary(self):
        with self._db.transaction() as conn:
            return self._deps.discovery_agent.coverage_summary(conn)

    # ------------------------------------------------------------------ #
    # feedback
    # ------------------------------------------------------------------ #

    def record_feedback_event(self, *, profile_id: str, event_type: str, apartment_id: str | None = None,
                               event_value: dict | None = None, search_id: str | None = None) -> FeedbackEvent:
        event = FeedbackEvent(
            profile_id=profile_id, event_type=event_type, event_value=event_value or {},
            occurred_at=datetime.now(timezone.utc), source="web_dashboard", metadata={},
            apartment_id=apartment_id, search_id=search_id,
        )
        with self._db.transaction() as conn:
            apartment = apartment_repository.get_apartment(conn, apartment_id) if apartment_id else None
            self._deps.feedback_engine.record_event(conn, event, apartment=apartment)
        return event

    def preference_profile(self, profile_id: str, *, mode: FeedbackMode = FeedbackMode.SUGGESTED):
        with self._db.transaction() as conn:
            return self._deps.feedback_engine.build_preference_profile(conn, profile_id, mode=mode)

    def explain_preference(self, profile_id: str, preference_key: str):
        with self._db.transaction() as conn:
            return self._deps.feedback_engine.explain_preference(conn, profile_id, preference_key)

    def preference_history(self, profile_id: str, preference_key: str):
        with self._db.transaction() as conn:
            return self._deps.feedback_engine.get_preference_history(conn, profile_id, preference_key)

    def undo_preference_adjustment(self, profile_id: str, preference_key: str, adjustment_id: int):
        with self._db.transaction() as conn:
            return self._deps.feedback_engine.undo_preference_adjustment(conn, profile_id, preference_key, adjustment_id)

    def reset_inferred_preferences(self, profile_id: str):
        with self._db.transaction() as conn:
            return self._deps.feedback_engine.reset_inferred_preferences(conn, profile_id)

    def export_feedback_history(self, profile_id: str):
        with self._db.transaction() as conn:
            return self._deps.feedback_engine.export_feedback_history(conn, profile_id)

    # ------------------------------------------------------------------ #
    # health / statistics
    # ------------------------------------------------------------------ #

    def system_health(self) -> WebHealth:
        with self._db.transaction() as conn:
            return WebHealth.collect(self._db, conn)

    def system_statistics(self) -> WebStatistics:
        with self._db.transaction() as conn:
            return WebStatistics.collect(conn, self._deps.configuration.data_dir / "rental_intelligence.db")
