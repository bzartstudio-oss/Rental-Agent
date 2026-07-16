"""`MonitoringEngine` — saved-search lifecycle (create/update/enable/disable)
and the mission's own 12-step monitoring workflow. See
docs/30_Continuous_Monitoring.md "Architecture"/"Monitoring Workflow".

Every heavy engine (`RentalResearchAgent`, `FilterEngine`, `GeographicEngine`,
`RankingEngineV2`, `FeedbackEngine`, `AutomaticDiscoveryAgent`) is reused
exactly as published — this module only adds orchestration, comparison, and
event generation on top.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.core.agent import RentalResearchAgent
from src.discovery import platform_registry
from src.discovery.automatic import AutomaticDiscoveryAgent, DiscoveryRequest
from src.feedback import FeedbackEngine
from src.feedback.models import FeedbackMode
from src.filter_engine import FilterConfiguration, FilterEngine
from src.geography import GeographicEngine
from src.monitoring import scheduling, service
from src.monitoring import statistics as monitoring_statistics
from src.monitoring.base_detector import MonitoringDetectionContext
from src.monitoring.deduplication import is_duplicate
from src.monitoring.exceptions import MonitoringConfigurationError, MonitoringValidationError
from src.monitoring.models import (
    MonitoringConfiguration,
    MonitoringEvent,
    MonitoringEventType,
    MonitoringPolicy,
    MonitoringRun,
    MonitoringRunStatus,
    MonitoringSchedule,
    SavedSearch,
    SavedSearchVersion,
)
from src.monitoring.registry import MonitoringRegistry
from src.ranking_v2 import RankingEngineV2
from src.ranking_v2.profile import RankingProfile
from src.ranking_v2.weights import RankingWeights
from src.search.search_request import SearchRequest
from src.search_memory import search_memory_service
from src.storage import search_memory_repository, search_repository
from src.storage.database import Database

_RUN_LIFECYCLE_SIGNIFICANCE = {
    MonitoringRunStatus.COMPLETED: 0.1,
    MonitoringRunStatus.PARTIAL: 0.4,
    MonitoringRunStatus.FAILED: 0.6,
}
_RUN_LIFECYCLE_EVENT_TYPE = {
    MonitoringRunStatus.COMPLETED: MonitoringEventType.MONITORING_RUN_COMPLETED,
    MonitoringRunStatus.PARTIAL: MonitoringEventType.MONITORING_RUN_PARTIAL,
    MonitoringRunStatus.FAILED: MonitoringEventType.MONITORING_RUN_FAILED,
}


class MonitoringEngine:
    def __init__(self, configuration: MonitoringConfiguration | None = None) -> None:
        self._configuration = configuration or MonitoringConfiguration()
        # Shared across every `_execute()` call this engine instance makes —
        # real, working geo-cache reuse *within one process's lifetime* ("reuse
        # cached geographic results when policy allows," the mission's own
        # words). `GeoCache` itself has no cross-process persistence (see
        # docs/30 "Known SQLite Limitations"), so a fresh CLI invocation always
        # starts cold regardless of policy — honestly documented, not hidden.
        self._shared_geo_engine = GeographicEngine()

    # ------------------------------------------------------------------ #
    # saved search lifecycle
    # ------------------------------------------------------------------ #

    def create_saved_search(
        self, db: Database, name: str, request: dict, *, profile_id: str | None = None,
        description: str | None = None, active_filters: dict | None = None, selected_platforms: list[str] | None = None,
        selected_connectors: list[str] | None = None, geographic_destinations: list | None = None,
        monitoring_policy: MonitoringPolicy | None = None, ranking_profile: dict | None = None,
        feedback_mode: str | None = None, report_options: dict | None = None, retention_policy: dict | None = None,
        tags: list[str] | None = None, metadata: dict | None = None, now: datetime | None = None,
    ) -> SavedSearch:
        if not name:
            raise MonitoringValidationError("SavedSearch.name is required")
        if not request.get("location"):
            raise MonitoringValidationError("SavedSearchVersion.request must include a 'location'")

        now = now or datetime.now(timezone.utc)
        saved_search_id = str(uuid.uuid4())
        policy = monitoring_policy or self._configuration.default_policy

        saved_search = SavedSearch(
            saved_search_id=saved_search_id, name=name, current_version=1, enabled=True, created_at=now,
            updated_at=now, profile_id=profile_id, description=description,
        )
        version = SavedSearchVersion(
            saved_search_id=saved_search_id, version=1, request=request, active_filters=active_filters or {},
            selected_platforms=selected_platforms or [], selected_connectors=selected_connectors or [],
            geographic_destinations=geographic_destinations or [], monitoring_policy=policy,
            report_options=report_options or {}, retention_policy=retention_policy or {}, tags=tags or [],
            metadata=metadata or {}, created_at=now, ranking_profile=ranking_profile, feedback_mode=feedback_mode,
        )
        with db.transaction() as conn:
            service.record_saved_search(conn, saved_search)
            service.record_saved_search_version(conn, version)
            service.record_schedule(
                conn, MonitoringSchedule(saved_search_id=saved_search_id, next_run_at=scheduling.compute_next_run_at(policy, now)),
            )
        return saved_search

    def update_saved_search(self, db: Database, saved_search_id: str, *, now: datetime | None = None, **overrides) -> SavedSearchVersion:
        """Creates a new immutable version — "Never overwrite a saved search
        definition" (the mission's own words). `overrides` may set any of
        `SavedSearchVersion`'s own fields; anything not given carries over
        unchanged from the current version.
        """
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            saved_search = service.get_saved_search(conn, saved_search_id)
            if saved_search is None:
                raise MonitoringValidationError(f"No such saved search {saved_search_id!r}")
            current = service.get_saved_search_version(conn, saved_search_id, saved_search.current_version)
            if current is None:
                raise MonitoringConfigurationError(f"Saved search {saved_search_id!r} has no version {saved_search.current_version}")

            fields = {
                "request": current.request, "active_filters": current.active_filters,
                "selected_platforms": current.selected_platforms, "selected_connectors": current.selected_connectors,
                "geographic_destinations": current.geographic_destinations, "monitoring_policy": current.monitoring_policy,
                "report_options": current.report_options, "retention_policy": current.retention_policy,
                "tags": current.tags, "metadata": current.metadata, "ranking_profile": current.ranking_profile,
                "feedback_mode": current.feedback_mode,
            }
            fields.update(overrides)

            new_version_number = saved_search.current_version + 1
            new_version = SavedSearchVersion(saved_search_id=saved_search_id, version=new_version_number, created_at=now, **fields)
            service.record_saved_search_version(conn, new_version)

            saved_search.current_version = new_version_number
            saved_search.updated_at = now
            service.update_saved_search(conn, saved_search)

            schedule = service.get_schedule(conn, saved_search_id) or MonitoringSchedule(saved_search_id=saved_search_id)
            schedule.next_run_at = scheduling.compute_next_run_at(new_version.monitoring_policy, now)
            service.update_schedule(conn, schedule)

        return new_version

    def set_enabled(self, db: Database, saved_search_id: str, enabled: bool, *, now: datetime | None = None) -> SavedSearch:
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            saved_search = service.get_saved_search(conn, saved_search_id)
            if saved_search is None:
                raise MonitoringValidationError(f"No such saved search {saved_search_id!r}")
            saved_search.enabled = enabled
            saved_search.updated_at = now
            service.update_saved_search(conn, saved_search)
        return saved_search

    # ------------------------------------------------------------------ #
    # execution
    # ------------------------------------------------------------------ #

    def run_now(self, db: Database, saved_search_id: str, *, now: datetime | None = None) -> MonitoringRun:
        """Manual trigger — "monitoring can run manually without any external
        scheduler" (the mission's own words): no claim required, runs
        regardless of the saved search's own schedule/interval policy.
        """
        return self._execute(db, saved_search_id, now=now or datetime.now(timezone.utc))

    def run_due(self, db: Database, *, worker_id: str | None = None, now: datetime | None = None) -> list[MonitoringRun]:
        """Scheduled execution — claims each due saved search before running
        it, so two concurrent callers can't both execute the same one.
        """
        worker_id = worker_id or self._configuration.default_worker_id
        now = now or datetime.now(timezone.utc)

        with db.transaction() as conn:
            due = scheduling.due_saved_searches(conn, now)

        runs = []
        for saved_search in due:
            with db.transaction() as conn:
                won_claim = scheduling.claim_due_run(
                    conn, saved_search.saved_search_id, worker_id, now, self._configuration.default_claim_ttl_minutes,
                )
            if won_claim:
                runs.append(self._execute(db, saved_search.saved_search_id, now=now))
        return runs

    def _execute(self, db: Database, saved_search_id: str, *, now: datetime) -> MonitoringRun:
        # Step 1-2: load saved search, resolve immutable version, check policy.
        with db.transaction() as conn:
            saved_search = service.get_saved_search(conn, saved_search_id)
            if saved_search is None:
                raise MonitoringValidationError(f"No such saved search {saved_search_id!r}")
            version = service.get_saved_search_version(conn, saved_search_id, saved_search.current_version)
            if version is None:
                raise MonitoringConfigurationError(f"Saved search {saved_search_id!r} has no version {saved_search.current_version}")
            policy = version.monitoring_policy
            previous_run = service.get_latest_run_for_saved_search(conn, saved_search_id)
            # Step 3: load approved active platforms — connector_available
            # already excludes unsupported platforms by construction (see
            # `platform_registry.list_connector_available_platforms`).
            allowed_platform_ids = self._resolve_allowed_platforms(conn, version, policy)

        run = MonitoringRun(
            saved_search_id=saved_search_id, saved_search_version=version.version, started_at=now,
            platforms_attempted=allowed_platform_ids,
        )
        with db.transaction() as conn:
            service.record_run(conn, run)

        # Step 4: optionally refresh platform discovery.
        discovery_comparison = None
        if policy.discovery_refresh_before_monitoring and version.geographic_destinations:
            discovery_comparison = self._refresh_discovery(db, version)

        # Step 5: execute Research Agent (updates Apartment History / Search
        # Memory / Knowledge Engine internally — see `core/agent.py::run()`).
        search_request = SearchRequest(location=version.request["location"], criteria=version.request.get("criteria", {}))
        research_agent = self._build_research_agent(db, saved_search, version, policy, allowed_platform_ids)

        try:
            search_result = research_agent.run(search_request)
        except Exception as exc:
            with db.transaction() as conn:
                run.status = MonitoringRunStatus.FAILED
                run.completed_at = datetime.now(timezone.utc)
                run.notes = f"Research agent run failed before any platform could be queried: {exc}"
                service.update_run(conn, run)
                self._record_lifecycle_event(conn, run)
                service.update_run(conn, run)  # event_count bump
                scheduling.mark_run_failed(conn, saved_search_id, run.completed_at, policy)
            return run

        with db.transaction() as conn:
            execution = search_memory_service.get_search_execution(conn, search_result.search_id)
            run.search_id = search_result.search_id
            run.platforms_succeeded = execution.searched_platform_ids if execution else []
            run.platforms_failed = execution.failed_platform_ids if execution else []
            run.status = self._determine_status(run.platforms_attempted, run.platforms_succeeded, run.platforms_failed)
            if policy.max_provider_failures is not None and len(run.platforms_failed) > policy.max_provider_failures:
                run.notes = f"Exceeded max_provider_failures policy ({len(run.platforms_failed)} > {policy.max_provider_failures})"

            # Step 6-9: compare with previous run + detect changes.
            comparison = None
            if previous_run is not None and previous_run.search_id is not None:
                comparison = search_memory_service.compare_searches(conn, previous_run.search_id, search_result.search_id)

            current_results = search_repository.get_search_results(conn, search_result.search_id)
            previous_results = (
                search_repository.get_search_results(conn, previous_run.search_id)
                if previous_run is not None and previous_run.search_id is not None else []
            )
            current_observed = search_memory_repository.get_observed_apartment_ids(conn, search_result.search_id)

            prior_runs = sorted(
                (r for r in service.get_runs_for_saved_search(conn, saved_search_id) if r.monitoring_run_id != run.monitoring_run_id),
                key=lambda r: r.started_at, reverse=True,
            )
            prior_observed_sets = [
                search_memory_repository.get_observed_apartment_ids(conn, r.search_id) for r in prior_runs if r.search_id is not None
            ]

            context = MonitoringDetectionContext(
                conn=conn, saved_search=saved_search, version=version, run=run, policy=policy, now=now,
                previous_run=previous_run, search_comparison=comparison, current_search_results=current_results,
                previous_search_results=previous_results, discovery_comparison=discovery_comparison,
                current_observed_apartment_ids=current_observed, prior_observed_apartment_sets=prior_observed_sets,
            )

            candidate_events: list[MonitoringEvent] = []
            for detector in MonitoringRegistry.all():
                candidate_events.extend(detector.detect(context))

            suppressed_count = 0
            for event in candidate_events:
                if event.significance < policy.minimum_change_significance:
                    continue
                if is_duplicate(conn, event.dedup_key, event.new_value, policy, now):
                    suppressed_count += 1
                    continue
                service.record_event(conn, event)

            # Step: run-lifecycle event.
            self._record_lifecycle_event(conn, run)

            run.event_count = len(service.get_events_for_run(conn, run.monitoring_run_id))
            service.update_run(conn, run)

            stats = monitoring_statistics.compute_statistics(
                conn, run.monitoring_run_id, suppressed_duplicate_count=suppressed_count,
                platforms_succeeded_count=len(run.platforms_succeeded), platforms_failed_count=len(run.platforms_failed),
                now=datetime.now(timezone.utc),
            )
            service.record_statistics(conn, stats)

        # Step 10: generate reports.
        if policy.generate_reports:
            from src.monitoring import report as monitoring_report

            with db.transaction() as conn:
                monitoring_report.generate_reports(conn, run, saved_search, version)
                report_event = MonitoringEvent(
                    saved_search_id=saved_search_id, saved_search_version=version.version, monitoring_run_id=run.monitoring_run_id,
                    search_id=run.search_id, event_type=MonitoringEventType.REPORT_GENERATED, severity="info", significance=0.1,
                    explanation="Monitoring reports generated", evidence={}, detected_at=datetime.now(timezone.utc),
                    dedup_key=f"{saved_search_id}:{run.monitoring_run_id}:{MonitoringEventType.REPORT_GENERATED}",
                )
                service.record_event(conn, report_event)
                run.event_count += 1
                service.update_run(conn, run)

        # Step 11: store run + statistics (already done above); release schedule/claim.
        with db.transaction() as conn:
            if run.status is MonitoringRunStatus.FAILED:
                scheduling.mark_run_failed(conn, saved_search_id, run.completed_at or datetime.now(timezone.utc), policy)
            elif run.status is MonitoringRunStatus.PARTIAL:
                scheduling.mark_run_partial(conn, saved_search_id, run.completed_at or datetime.now(timezone.utc), policy)
            else:
                scheduling.mark_run_completed(conn, saved_search_id, run.completed_at or datetime.now(timezone.utc), policy)

        return run

    # ------------------------------------------------------------------ #

    def _resolve_allowed_platforms(self, conn, version: SavedSearchVersion, policy: MonitoringPolicy) -> list[str]:
        allowed = []
        for platform in platform_registry.list_connector_available_platforms(conn):
            if version.selected_platforms and platform.id not in version.selected_platforms:
                continue
            if version.selected_connectors and platform.connector_name not in version.selected_connectors:
                continue
            if platform.connector_name in policy.disabled_providers:
                continue
            if policy.enabled_providers is not None and platform.connector_name not in policy.enabled_providers:
                continue
            allowed.append(platform.id)
        return allowed

    def _refresh_discovery(self, db: Database, version: SavedSearchVersion):
        destination = version.geographic_destinations[0] if version.geographic_destinations else None
        if not isinstance(destination, dict):
            return None

        discovery_agent = AutomaticDiscoveryAgent()
        with db.transaction() as conn:
            previous = discovery_agent.latest_discovery(conn)

        discovery_request = DiscoveryRequest(country=destination.get("country"), region=destination.get("region"), city=destination.get("city"))
        with db.transaction() as conn:
            result = discovery_agent.run(conn, discovery_request)

        if previous is None:
            return None
        with db.transaction() as conn:
            return discovery_agent.compare_discovery_runs(conn, previous.run_id, result.run.run_id)

    def _build_research_agent(
        self, db: Database, saved_search: SavedSearch, version: SavedSearchVersion, policy: MonitoringPolicy, allowed_platform_ids: list[str],
    ) -> RentalResearchAgent:
        filter_engine = None
        if version.active_filters:
            enabled_keys = version.active_filters.get("enabled_filter_keys")
            filter_engine = FilterEngine(FilterConfiguration(
                enabled_filter_keys=set(enabled_keys) if enabled_keys else None,
                strict_validation=version.active_filters.get("strict_validation", False),
            ))

        geo_engine = GeographicEngine() if policy.force_fresh_geo else (self._shared_geo_engine if policy.use_cached_geo else None)

        ranking_profile = None
        if version.ranking_profile:
            ranking_profile = RankingProfile(
                name=version.ranking_profile.get("name", "custom"), description=version.ranking_profile.get("description", ""),
                weights=RankingWeights(values=version.ranking_profile["weights"]),
            )
        ranking_engine_v2 = RankingEngineV2(profile=ranking_profile)

        feedback_engine = FeedbackEngine() if (version.feedback_mode and saved_search.profile_id) else None

        return RentalResearchAgent(
            db, filter_engine=filter_engine, geo_engine=geo_engine, ranking_engine_v2=ranking_engine_v2,
            feedback_engine=feedback_engine, feedback_profile_id=saved_search.profile_id if feedback_engine else None,
            feedback_mode=FeedbackMode(version.feedback_mode) if (feedback_engine and version.feedback_mode) else FeedbackMode.SUGGESTED,
            allowed_platform_ids=allowed_platform_ids,
        )

    def _determine_status(self, attempted: list[str], succeeded: list[str], failed: list[str]) -> MonitoringRunStatus:
        if not attempted:
            return MonitoringRunStatus.FAILED
        if not failed:
            return MonitoringRunStatus.COMPLETED
        if succeeded:
            return MonitoringRunStatus.PARTIAL
        return MonitoringRunStatus.FAILED

    def _record_lifecycle_event(self, conn, run: MonitoringRun) -> None:
        if run.completed_at is None:
            run.completed_at = datetime.now(timezone.utc)
        event_type = _RUN_LIFECYCLE_EVENT_TYPE[run.status]
        significance = _RUN_LIFECYCLE_SIGNIFICANCE[run.status]
        service.record_event(
            conn,
            MonitoringEvent(
                saved_search_id=run.saved_search_id, saved_search_version=run.saved_search_version,
                monitoring_run_id=run.monitoring_run_id, search_id=run.search_id, event_type=event_type,
                severity="critical" if run.status is MonitoringRunStatus.FAILED else ("warning" if run.status is MonitoringRunStatus.PARTIAL else "info"),
                significance=significance, explanation=f"Monitoring run {run.status.value}", evidence={
                    "platforms_attempted": run.platforms_attempted, "platforms_succeeded": run.platforms_succeeded,
                    "platforms_failed": run.platforms_failed,
                },
                detected_at=run.completed_at, dedup_key=f"{run.saved_search_id}:{run.monitoring_run_id}:{event_type}",
            ),
        )
