"""Job-runner + job-persistence tests — see docs/32_Web_Dashboard.md "Job
Model".
"""

from __future__ import annotations

import time
import unittest

from src.web.constants import JOB_TYPE_SEARCH, TERMINAL_JOB_STATUSES
from src.web.jobs import service as jobs_service
from src.web.jobs.models import Job
from src.web.jobs.runner import JobRunner
from tests.web.helpers import web_test_app


def _wait_for_terminal(db, job_id: str, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.2)
    raise TimeoutError(f"job {job_id} never reached a terminal state")


class JobPersistenceTests(unittest.TestCase):
    def test_job_survives_a_fresh_read_from_the_database(self) -> None:
        with web_test_app() as (app, db, tmp):
            job = Job(job_type=JOB_TYPE_SEARCH, profile_id="p1")
            with db.transaction() as conn:
                jobs_service.record_job(conn, job)

            with db.transaction() as conn:
                reloaded = jobs_service.get_job(conn, job.job_id)
            self.assertEqual(reloaded.job_id, job.job_id)
            self.assertEqual(reloaded.status, "pending")

    def test_cancellation_request_is_persisted(self) -> None:
        with web_test_app() as (app, db, tmp):
            job = Job(job_type=JOB_TYPE_SEARCH)
            with db.transaction() as conn:
                jobs_service.record_job(conn, job)
                jobs_service.request_cancellation(conn, job.job_id)
                reloaded = jobs_service.get_job(conn, job.job_id)
            self.assertTrue(reloaded.cancellation_requested)

    def test_cancellation_is_a_no_op_on_a_terminal_job(self) -> None:
        with web_test_app() as (app, db, tmp):
            job = Job(job_type=JOB_TYPE_SEARCH, status="completed")
            with db.transaction() as conn:
                jobs_service.record_job(conn, job)
                jobs_service.request_cancellation(conn, job.job_id)
                reloaded = jobs_service.get_job(conn, job.job_id)
            self.assertFalse(reloaded.cancellation_requested)

    def test_unknown_job_id_returns_none(self) -> None:
        with web_test_app() as (app, db, tmp):
            with db.transaction() as conn:
                self.assertIsNone(jobs_service.get_job(conn, "no-such-job"))


class JobRunnerSearchTests(unittest.TestCase):
    def test_a_search_job_runs_to_a_terminal_state_and_records_a_search_id(self) -> None:
        with web_test_app() as (app, db, tmp):
            runner = JobRunner(db)
            job = runner.start_search_job(
                profile_id="p1", location="Example City", criteria={}, label=None,
                use_filter_engine=False, use_geo_engine=False, ranking_profile=None,
                feedback_mode=None, allowed_platform_ids=None,
            )
            final = _wait_for_terminal(db, job.job_id)
            self.assertIn(final.status, {"completed", "partial"})
            self.assertIsNotNone(final.result_reference)

    def test_a_failed_search_job_records_an_error_summary_not_a_traceback(self) -> None:
        with web_test_app() as (app, db, tmp):
            runner = JobRunner(db)
            # An empty location bypasses form validation (this calls the
            # runner directly) and reaches `SearchRequest.__post_init__`,
            # which raises — proving a raised exception inside the
            # background thread becomes an honest FAILED job, never an
            # unhandled thread crash.
            job = runner.start_search_job(
                profile_id="p1", location="", criteria={}, label=None,
                use_filter_engine=False, use_geo_engine=False, ranking_profile=None,
                feedback_mode=None, allowed_platform_ids=None,
            )
            final = _wait_for_terminal(db, job.job_id)
            self.assertEqual(final.status, "failed")
            self.assertIsNotNone(final.error_summary)


if __name__ == "__main__":
    unittest.main()
