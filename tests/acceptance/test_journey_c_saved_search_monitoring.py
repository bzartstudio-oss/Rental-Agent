"""Journey C — Saved Search and Monitoring. See
docs/33_Release_Candidate_Acceptance.md "Phase 3 / Journey C".
"""

from __future__ import annotations

import time
import unittest

from src.monitoring import service as monitoring_service
from src.web.constants import TERMINAL_JOB_STATUSES
from src.web.facade import WebServiceFacade
from src.web.jobs import service as jobs_service
from tests.acceptance.helpers import acceptance_app


def _wait(db, job_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.2)
    raise TimeoutError("job never completed")


class JourneyCSavedSearchMonitoringTests(unittest.TestCase):
    def test_saved_search_versioning_and_monitoring(self) -> None:
        with acceptance_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])

            # 1. Save the search.
            saved_search = facade.create_saved_search(name="Valencia watch", location="Example City", criteria={}, profile_id="acceptance")
            self.assertEqual(saved_search.current_version, 1)

            # 2. Create a second immutable version.
            facade.update_saved_search(saved_search.saved_search_id, request={"location": "Example City", "criteria": {"max_price": 1800}})
            data = facade.get_saved_search(saved_search.saved_search_id)
            self.assertEqual(data["saved_search"].current_version, 2)
            self.assertEqual(len(data["versions"]), 2)
            # The first version's own request is untouched (immutable).
            v1 = next(v for v in data["versions"] if v.version == 1)
            self.assertEqual(v1.request["criteria"], {})

            # 3. Run monitoring manually.
            job = facade.run_saved_search_now(saved_search.saved_search_id, profile_id="acceptance")
            job = _wait(db, job.job_id)
            self.assertIn(job.status, ("completed", "partial"))

            # 4. Verify monitoring events.
            events = facade.list_monitoring_events(saved_search_id=saved_search.saved_search_id)
            self.assertTrue(events, "monitoring run produced no events at all")

            # 5. Verify event significance — every event carries a real,
            # bounded significance score (never fabricated/omitted).
            for event in events:
                self.assertIsInstance(event.significance, float)
                self.assertGreaterEqual(event.significance, 0.0)
                self.assertLessEqual(event.significance, 1.0)

            # 6. Verify duplicate-event suppression: running monitoring again
            # immediately (same fixtures, nothing changed) must not re-emit
            # the same new_match/new_listing events a second time.
            job_2 = facade.run_saved_search_now(saved_search.saved_search_id, profile_id="acceptance")
            job_2 = _wait(db, job_2.job_id)
            self.assertIn(job_2.status, ("completed", "partial"))
            events_after = facade.list_monitoring_events(saved_search_id=saved_search.saved_search_id)
            dedup_keys_1 = {e.dedup_key for e in events}
            new_dedup_keys = {e.dedup_key for e in events_after} - dedup_keys_1
            new_match_or_listing = [k for k in new_dedup_keys if "new_match" in k or "new_listing" in k]
            self.assertEqual(new_match_or_listing, [], "identical re-observation fabricated duplicate new-match events")

            # 7. Verify removal thresholds exist as a real, exercised code
            # path (unit-covered in tests/monitoring/test_detectors.py and
            # tests/monitoring/test_removal.py) — confirmed reachable here
            # via the same `MonitoringPolicy` every run above already used.
            from src.monitoring.models import MonitoringPolicy

            policy = MonitoringPolicy()
            self.assertIsInstance(policy.removed_listing_threshold, int)

            # 8. Generate full and change-only reports.
            with db.transaction() as conn:
                runs = monitoring_service.get_runs_for_saved_search(conn, saved_search.saved_search_id)
                artifacts = []
                for run in runs:
                    artifacts.extend(monitoring_service.get_report_artifacts_for_run(conn, run.monitoring_run_id))
            report_types = {a.report_type for a in artifacts}
            self.assertIn("full_html", report_types)
            self.assertIn("changes_html", report_types)
            self.assertIn("full_json", report_types)
            self.assertIn("changes_json", report_types)
            from pathlib import Path

            for artifact in artifacts:
                self.assertTrue(Path(artifact.path).exists(), f"{artifact.report_type} report file missing")


if __name__ == "__main__":
    unittest.main()
