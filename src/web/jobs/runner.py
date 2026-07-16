"""`JobRunner` — a local, thread-based job execution abstraction. See
docs/32_Web_Dashboard.md "Job Model"/"Future Task-Queue Migration".

Runs one job per background `threading.Thread` against the *same* SQLite
file the rest of the app uses (`Database.transaction()` opens its own
connection per call, exactly like every other caller in this codebase — see
`storage/database.py`'s own docstring on why that's safe for SQLite). No
Redis/Celery: correct and sufficient for one local user, one process.

Future task-queue migration: every method here takes a `Job` already
persisted and mutates it via `jobs.service` — swapping the body of `_run_*`
to instead enqueue a message onto a real broker (and have a separate worker
process call the same `_execute_search`/`_execute_monitoring_run`/
`_execute_discovery_run` functions) would not change any route, form, or
template; those all only ever see `Job` records via `jobs.service.get_job()`.
That's the one seam a real queue would plug into.
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime, timezone

from src.core.agent import RentalResearchAgent
from src.core.config import OUTPUT_DIR
from src.discovery.automatic.agent import AutomaticDiscoveryAgent
from src.discovery.automatic.models import DiscoveryRequest
from src.feedback.engine import FeedbackEngine
from src.feedback.models import FeedbackMode
from src.filter_engine import FilterConfiguration, FilterEngine
from src.geography import GeographicEngine
from src.monitoring.engine import MonitoringEngine
from src.monitoring.models import MonitoringRunStatus
from src.ranking_v2 import RankingEngineV2
from src.ranking_v2.profile import RankingProfile
from src.ranking_v2.weights import RankingWeights
from src.search.search_request import SearchRequest
from src.search_memory import search_memory_service
from src.storage.database import Database
from src.web.constants import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PARTIAL,
    JOB_STATUS_RUNNING,
    JOB_TYPE_DISCOVERY_RUN,
    JOB_TYPE_MONITORING_RUN,
    JOB_TYPE_SEARCH,
)
from src.web.jobs import service as jobs_service
from src.web.jobs.models import Job


def _serialize_ranking_v2(results) -> dict:
    """A small, purely presentational snapshot of `RankedApartmentV2` keyed by
    apartment id — see `core/agent.py::SearchRunResult.ranking_v2_results`'s
    own docstring for why this is captured here rather than recomputed later.
    """
    if not results:
        return {}
    return {
        entry.apartment_id: {
            "rank": entry.rank,
            "final_score": entry.final_score,
            "confidence": entry.confidence.overall,
            "confidence_per_rule": entry.confidence.per_rule,
            "top_positive_factors": entry.explanation.top_positive_factors,
            "top_negative_factors": entry.explanation.top_negative_factors,
            "all_reasons": entry.explanation.all_reasons,
            "warnings": entry.warnings,
        }
        for entry in results
    }


class JobRunner:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # search jobs
    # ------------------------------------------------------------------ #

    def start_search_job(self, *, profile_id: str | None, location: str, criteria: dict, label: str | None,
                          use_filter_engine: bool, use_geo_engine: bool, ranking_profile: RankingProfile | None,
                          feedback_mode: FeedbackMode | None, allowed_platform_ids: list[str] | None) -> Job:
        job = Job(job_type=JOB_TYPE_SEARCH, profile_id=profile_id, metadata={"location": location, "label": label})
        with self._db.transaction() as conn:
            jobs_service.record_job(conn, job)

        thread = threading.Thread(
            target=self._run_search,
            args=(job.job_id, profile_id, location, criteria, label, use_filter_engine, use_geo_engine,
                  ranking_profile, feedback_mode, allowed_platform_ids),
            daemon=True,
        )
        thread.start()
        return job

    def _run_search(self, job_id, profile_id, location, criteria, label, use_filter_engine, use_geo_engine,
                     ranking_profile, feedback_mode, allowed_platform_ids) -> None:
        now = datetime.now(timezone.utc)
        with self._db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
            job.status = JOB_STATUS_RUNNING
            job.started_at = now
            job.current_stage = "running_research_agent"
            jobs_service.update_job(conn, job)

        try:
            request = SearchRequest(location=location, criteria=criteria, label=label)
            filter_engine = FilterEngine(FilterConfiguration()) if use_filter_engine else None
            geo_engine = GeographicEngine() if use_geo_engine else None
            ranking_engine_v2 = RankingEngineV2(profile=ranking_profile) if ranking_profile is not None else None
            feedback_engine = FeedbackEngine() if (feedback_mode is not None and profile_id) else None

            agent = RentalResearchAgent(
                self._db, output_dir=OUTPUT_DIR, filter_engine=filter_engine, geo_engine=geo_engine,
                ranking_engine_v2=ranking_engine_v2, feedback_engine=feedback_engine,
                feedback_profile_id=profile_id if feedback_engine else None,
                feedback_mode=feedback_mode or FeedbackMode.SUGGESTED,
                allowed_platform_ids=allowed_platform_ids,
            )
            result = agent.run(request)
        except Exception as exc:  # noqa: BLE001 — a failed job must never crash the thread silently
            with self._db.transaction() as conn:
                job = jobs_service.get_job(conn, job_id)
                job.status = JOB_STATUS_FAILED
                job.error_summary = f"{type(exc).__name__}: {exc}"
                job.completed_at = datetime.now(timezone.utc)
                jobs_service.update_job(conn, job)
            return

        with self._db.transaction() as conn:
            execution = search_memory_service.get_search_execution(conn, result.search_id)
            job = jobs_service.get_job(conn, job_id)
            job.result_reference = result.search_id
            job.progress = 1.0
            job.current_stage = "completed"
            job.completed_at = datetime.now(timezone.utc)
            failed = execution.failed_platform_ids if execution else []
            searched = execution.searched_platform_ids if execution else []
            if failed and (searched or result.apartments):
                job.status = JOB_STATUS_PARTIAL
                job.warnings = [f"Platform {pid!r} failed during this search" for pid in failed]
            elif failed and not searched and not result.apartments:
                job.status = JOB_STATUS_FAILED
                job.error_summary = f"Every attempted platform failed: {', '.join(failed)}"
            else:
                job.status = JOB_STATUS_COMPLETED
            if job.metadata.get("ranking_v2") is None and result.ranking_v2_results:
                job.metadata = {**job.metadata, "ranking_v2": _serialize_ranking_v2(result.ranking_v2_results)}
            jobs_service.update_job(conn, job)

    # ------------------------------------------------------------------ #
    # monitoring-run jobs
    # ------------------------------------------------------------------ #

    def start_monitoring_run_job(self, *, profile_id: str | None, saved_search_id: str) -> Job:
        job = Job(job_type=JOB_TYPE_MONITORING_RUN, profile_id=profile_id, request_reference=saved_search_id)
        with self._db.transaction() as conn:
            jobs_service.record_job(conn, job)

        thread = threading.Thread(target=self._run_monitoring, args=(job.job_id, saved_search_id), daemon=True)
        thread.start()
        return job

    def _run_monitoring(self, job_id: str, saved_search_id: str) -> None:
        with self._db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
            job.status = JOB_STATUS_RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.current_stage = "running_monitoring_engine"
            jobs_service.update_job(conn, job)

        engine = MonitoringEngine()
        try:
            run = engine.run_now(self._db, saved_search_id)
        except Exception as exc:  # noqa: BLE001
            with self._db.transaction() as conn:
                job = jobs_service.get_job(conn, job_id)
                job.status = JOB_STATUS_FAILED
                job.error_summary = f"{type(exc).__name__}: {exc}"
                job.completed_at = datetime.now(timezone.utc)
                jobs_service.update_job(conn, job)
            return

        status_map = {
            MonitoringRunStatus.COMPLETED: JOB_STATUS_COMPLETED,
            MonitoringRunStatus.PARTIAL: JOB_STATUS_PARTIAL,
            MonitoringRunStatus.FAILED: JOB_STATUS_FAILED,
        }
        with self._db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
            job.result_reference = run.monitoring_run_id
            job.progress = 1.0
            job.current_stage = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.status = status_map.get(run.status, JOB_STATUS_FAILED)
            if run.notes:
                job.warnings = [run.notes]
            jobs_service.update_job(conn, job)

    # ------------------------------------------------------------------ #
    # discovery-run jobs
    # ------------------------------------------------------------------ #

    def start_discovery_run_job(self, *, profile_id: str | None, country: str | None, region: str | None,
                                 city: str | None, rental_categories: list[str] | None = None) -> Job:
        job = Job(
            job_type=JOB_TYPE_DISCOVERY_RUN, profile_id=profile_id,
            metadata={"country": country, "region": region, "city": city, "rental_categories": rental_categories or []},
        )
        with self._db.transaction() as conn:
            jobs_service.record_job(conn, job)

        thread = threading.Thread(
            target=self._run_discovery, args=(job.job_id, country, region, city, rental_categories), daemon=True,
        )
        thread.start()
        return job

    def _run_discovery(self, job_id: str, country, region, city, rental_categories) -> None:
        with self._db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
            job.status = JOB_STATUS_RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.current_stage = "running_discovery_agent"
            jobs_service.update_job(conn, job)

        agent = AutomaticDiscoveryAgent()
        try:
            request = DiscoveryRequest(country=country, region=region, city=city, rental_categories=rental_categories or [])
            with self._db.transaction() as conn:
                result = agent.run(conn, request)
        except Exception as exc:  # noqa: BLE001
            with self._db.transaction() as conn:
                job = jobs_service.get_job(conn, job_id)
                job.status = JOB_STATUS_FAILED
                job.error_summary = f"{type(exc).__name__}: {exc}"
                job.completed_at = datetime.now(timezone.utc)
                jobs_service.update_job(conn, job)
            return

        with self._db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
            job.result_reference = result.run.run_id
            job.progress = 1.0
            job.current_stage = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.status = JOB_STATUS_COMPLETED
            job.warnings = result.warnings
            jobs_service.update_job(conn, job)
