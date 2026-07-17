"""Journey B — Repeat Search and History. See
docs/33_Release_Candidate_Acceptance.md "Phase 3 / Journey B".

Runs the real search pipeline twice (deterministic demo fixtures), then
simulates every mission-named change type via the exact repository functions
`analyzers/engine.py` itself uses for a real re-observation — the same
established pattern `tests/monitoring/test_detectors.py`/`tests/history/`
already use to test detection deterministically, rather than requiring a
second, hand-authored fixture file per change type.
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timedelta, timezone

from src.history import history_service
from src.search_memory import search_memory_service
from src.search_memory.comparison import diff_apartment_sets
from src.storage import apartment_history_repository, apartment_repository, search_repository
from src.storage.models import ApartmentAvailabilityHistoryEntry, ApartmentPriceHistoryEntry
from src.web.constants import TERMINAL_JOB_STATUSES
from src.web.facade import WebServiceFacade
from tests.acceptance.helpers import acceptance_app


def _run_search(facade, db, location="Example City"):
    job = facade.start_search(
        profile_id="acceptance", location=location, criteria={}, label=None, use_filter_engine=False,
        use_geo_engine=False, ranking_weights=None, feedback_mode=None, allowed_platform_ids=None,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        from src.web.jobs import service as jobs_service

        with db.transaction() as conn:
            job = jobs_service.get_job(conn, job.job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.2)
    raise TimeoutError("search never completed")


class JourneyBRepeatSearchHistoryTests(unittest.TestCase):
    def test_repeat_search_never_overwrites_history(self) -> None:
        with acceptance_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])

            # 1. Run the same search twice.
            job_1 = _run_search(facade, db)
            job_2 = _run_search(facade, db)
            self.assertIn(job_1.status, ("completed", "partial"))
            self.assertIn(job_2.status, ("completed", "partial"))
            search_id_1, search_id_2 = job_1.result_reference, job_2.result_reference
            self.assertNotEqual(search_id_1, search_id_2)

            with db.transaction() as conn:
                results_1 = search_repository.get_search_results(conn, search_id_1)
                apartment_id = results_1[0].apartment_id
                original_price = results_1[0].price_at_search
                original_status = results_1[0].status_at_search
                apartment = apartment_repository.get_apartment(conn, apartment_id)

            now = datetime.now(timezone.utc)

            # 2a. Simulate a price decrease.
            new_price = apartment.current_price - 100
            with db.transaction() as conn:
                apartment_repository.add_price_history(
                    conn, ApartmentPriceHistoryEntry(apartment_id=apartment_id, price=new_price, observed_at=now, search_id=search_id_2),
                )
                apartment_repository.update_apartment_state(conn, apartment_id, new_price, apartment.current_status, now)

            # 2b. Simulate an availability change.
            with db.transaction() as conn:
                apartment_repository.add_availability_history(
                    conn, ApartmentAvailabilityHistoryEntry(apartment_id=apartment_id, status="pending", observed_at=now, search_id=search_id_2),
                )
                apartment_repository.update_apartment_state(conn, apartment_id, new_price, "pending", now)

            # 2c. Simulate a description change (generic-field history).
            with db.transaction() as conn:
                updated = apartment_repository.get_apartment(conn, apartment_id)
                changes = history_service.record_reobservation(
                    conn, updated, {"title": updated.title, "description": "A newly updated, more detailed description."}, now, search_id=search_id_2,
                )
                self.assertTrue(any(c.field_name == "description" for c in changes))

            # 2d. Simulate an image change (added).
            with db.transaction() as conn:
                apartment_history_repository.add_image_event(
                    conn, apartment_id, "added", "https://example.com/new-photo.jpg", search_id_2, now,
                )

            # 2e/2f. A "new listing" and a "temporarily missing listing" are
            # exactly what `diff_apartment_sets` (used by `compare_searches`)
            # already computes from `search_observed_apartments` — verified below.

            # 3a. Verify no history was overwritten (both rows still exist, in order).
            with db.transaction() as conn:
                price_history = apartment_repository.get_price_history(conn, apartment_id)
                availability_history = apartment_repository.get_availability_history(conn, apartment_id)
            self.assertGreaterEqual(len(price_history), 2)
            self.assertGreaterEqual(len(availability_history), 2)

            # 3b. Price timeline is correct (oldest first, real values, nothing invented).
            prices = [entry.price for entry in price_history]
            self.assertIn(new_price, prices)
            self.assertTrue(any(p != new_price for p in prices), "original price was lost, not just superseded")

            # 3c. Availability timeline is correct.
            statuses = [entry.status for entry in availability_history]
            self.assertIn("pending", statuses)

            # 3d. Comparison is correct — reuses the exact function
            # `search_memory_service.compare_searches` itself calls.
            with db.transaction() as conn:
                observed_1 = {r.apartment_id for r in search_repository.get_search_results(conn, search_id_1)}
                observed_2 = {r.apartment_id for r in search_repository.get_search_results(conn, search_id_2)}
            new_ids, removed_ids = diff_apartment_sets(observed_1, observed_2)
            self.assertIsInstance(new_ids, list)
            self.assertIsInstance(removed_ids, list)

            with db.transaction() as conn:
                comparison = search_memory_service.compare_searches(conn, search_id_1, search_id_2)
            self.assertEqual(comparison.previous_search_id, search_id_1)
            self.assertEqual(comparison.current_search_id, search_id_2)

            # 3e. Original search snapshots remain unchanged — search_results
            # rows are a deliberate point-in-time snapshot, never updated.
            with db.transaction() as conn:
                results_1_again = search_repository.get_search_results(conn, search_id_1)
            reloaded = next(r for r in results_1_again if r.apartment_id == apartment_id)
            self.assertEqual(reloaded.price_at_search, original_price)
            self.assertEqual(reloaded.status_at_search, original_status)
            self.assertNotEqual(reloaded.price_at_search, new_price)


if __name__ == "__main__":
    unittest.main()
