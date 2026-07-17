"""Journey E — Feedback and Ranking. See
docs/33_Release_Candidate_Acceptance.md "Phase 3 / Journey E".
"""

from __future__ import annotations

import time
import unittest

from src.feedback.models import FeedbackMode
from src.ranking_v2 import DEFAULT_PROFILE
from src.web.constants import TERMINAL_JOB_STATUSES
from src.web.facade import WebServiceFacade
from src.web.jobs import service as jobs_service
from tests.acceptance.helpers import acceptance_app

# Every listed "sensitive trait" a feedback rule could theoretically infer
# but must never be a registered preference key for — race, religion,
# nationality, health, sexual orientation, etc. See
# docs/28_User_Feedback_and_Preference_Learning.md "Privacy Boundaries".
_FORBIDDEN_PREFERENCE_SUBSTRINGS = ("race", "religion", "ethnicity", "nationality", "health", "disability", "sexual", "immigration")


def _wait(db, job_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.2)
    raise TimeoutError("job never completed")


class JourneyEFeedbackRankingTests(unittest.TestCase):
    def test_feedback_and_ranking_journey(self) -> None:
        with acceptance_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])

            # 1-2. Start with an explicit ranking profile; rank several apartments.
            self.assertTrue(DEFAULT_PROFILE.weights.values)
            job = facade.start_search(
                profile_id="acceptance", location="Example City", criteria={}, label=None, use_filter_engine=False,
                use_geo_engine=False, ranking_weights=None, feedback_mode=None, allowed_platform_ids=None,
            )
            job = _wait(db, job.job_id)
            self.assertIn(job.status, ("completed", "partial"))
            data = facade.search_results(job.result_reference)
            apartment_ids = list(data["apartments"])
            self.assertGreaterEqual(len(apartment_ids), 2)

            # 3. Save, shortlist, reject, and rate results.
            facade.record_feedback_event(profile_id="acceptance", event_type="saved", apartment_id=apartment_ids[0])
            facade.record_feedback_event(profile_id="acceptance", event_type="shortlisted", apartment_id=apartment_ids[0])
            facade.record_feedback_event(profile_id="acceptance", event_type="rejected", apartment_id=apartment_ids[1])
            facade.record_feedback_event(profile_id="acceptance", event_type="manual_rating", apartment_id=apartment_ids[0], event_value={"rating": 5})

            # 4. Rebuild the preference profile.
            profile = facade.preference_profile("acceptance", mode=FeedbackMode.SUGGESTED)
            self.assertEqual(profile.profile_id, "acceptance")
            self.assertTrue(profile.preferences)

            # 5. Compare EXPLICIT_ONLY, SUGGESTED, and ASSISTED modes.
            explicit_only = facade.preference_profile("acceptance", mode=FeedbackMode.EXPLICIT_ONLY)
            suggested = facade.preference_profile("acceptance", mode=FeedbackMode.SUGGESTED)
            assisted = facade.preference_profile("acceptance", mode=FeedbackMode.ASSISTED)
            self.assertEqual(explicit_only.mode, FeedbackMode.EXPLICIT_ONLY)
            self.assertEqual(suggested.mode, FeedbackMode.SUGGESTED)
            self.assertEqual(assisted.mode, FeedbackMode.ASSISTED)
            # Every mode considers the same registered preference keys —
            # they differ in *how* a value is computed, not *which* keys exist.
            self.assertEqual(set(explicit_only.preferences), set(suggested.preferences))
            self.assertEqual(set(suggested.preferences), set(assisted.preferences))

            # 6. Verify all changes are explainable and reversible.
            some_key = next(iter(profile.preferences))
            evidence = facade.explain_preference("acceptance", some_key)
            self.assertEqual(evidence.preference_key, some_key)
            history = facade.preference_history("acceptance", some_key)
            self.assertTrue(history, "no adjustment history recorded for a preference that has real evidence")
            if history:
                undone = facade.undo_preference_adjustment("acceptance", some_key, history[-1].id)
                self.assertEqual(undone.adjustment_type, "undo")
                self.assertEqual(undone.reverses_adjustment_id, history[-1].id)

            reset_adjustments = facade.reset_inferred_preferences("acceptance")
            self.assertIsInstance(reset_adjustments, list)
            for adjustment in reset_adjustments:
                self.assertEqual(adjustment.adjustment_type, "reset")

            # 7. Verify no sensitive traits are inferred — every registered
            # preference key is checked against a hard denylist.
            for key in profile.preferences:
                lowered = key.lower()
                for forbidden in _FORBIDDEN_PREFERENCE_SUBSTRINGS:
                    self.assertNotIn(forbidden, lowered, f"preference key {key!r} appears to infer a sensitive trait")


if __name__ == "__main__":
    unittest.main()
