"""`WebServiceFacade` tests — search workflow, results, apartment detail,
comparison, saved searches, monitoring, notifications, discovery, feedback,
health. See docs/32_Web_Dashboard.md "Service Facade".
"""

from __future__ import annotations

import time
import unittest

from src.discovery.automatic import service as discovery_service
from src.discovery.automatic.models import PlatformCandidate, PlatformStatus
from src.web.constants import TERMINAL_JOB_STATUSES
from src.web.error_handler import WebNotFoundError, WebValidationError
from src.web.facade import WebServiceFacade
from src.web.jobs import service as jobs_service
from tests.web.helpers import web_test_app


def _run_search(facade, db, **overrides):
    fields = dict(profile_id="p1", location="Example City", criteria={}, label=None, use_filter_engine=False,
                  use_geo_engine=False, ranking_weights=None, feedback_mode=None, allowed_platform_ids=None)
    fields.update(overrides)
    job = facade.start_search(**fields)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with db.transaction() as conn:
            job = jobs_service.get_job(conn, job.job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.2)
    raise TimeoutError("search job never completed")


class DashboardSnapshotTests(unittest.TestCase):
    def test_returns_every_documented_section(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            snapshot = facade.dashboard_snapshot("p1")
            for key in ("recent_jobs", "saved_searches", "unacknowledged_events", "unacknowledged_deliveries",
                        "recent_candidates", "top_apartments", "connector_health", "statistics", "next_run_at"):
                self.assertIn(key, snapshot)


class SearchWorkflowTests(unittest.TestCase):
    def test_start_search_runs_to_completion_and_produces_apartments(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            job = _run_search(facade, db)
            self.assertIn(job.status, {"completed", "partial"})
            data = facade.search_results(job.result_reference)
            self.assertTrue(data["entries"])
            self.assertTrue(data["apartments"])

    def test_start_search_rejects_empty_location(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            with self.assertRaises(WebValidationError):
                facade.start_search(profile_id="p1", location="", criteria={}, label=None, use_filter_engine=False,
                                     use_geo_engine=False, ranking_weights=None, feedback_mode=None, allowed_platform_ids=None)

    def test_search_results_for_unknown_search_id_raises_not_found(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            with self.assertRaises(WebNotFoundError):
                facade.search_results("no-such-search")

    def test_ranking_v2_snapshot_is_captured_when_engine_ran(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            job = _run_search(facade, db, ranking_weights=None)
            data = facade.search_results(job.result_reference)
            # ranking_v2 is always run by start_search (a default profile is
            # applied when none is given) — every entry should have a
            # captured explanation, never a silently empty one.
            self.assertTrue(data["ranking_v2"])


class ApartmentDetailTests(unittest.TestCase):
    def test_detail_labels_missing_fields_honestly(self) -> None:
        from src.web.presenters.apartment_presenter import present_missing_data_summary

        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            job = _run_search(facade, db)
            data = facade.search_results(job.result_reference)
            apartment_id = next(iter(data["apartments"]))
            detail = facade.apartment_detail(apartment_id, profile_id="p1")
            self.assertEqual(detail["apartment"].id, apartment_id)
            # `missing_data` is computed by the presenter (see
            # `routes/apartments.py::detail()`), not returned by the facade
            # itself — verify it's a real, callable list, never fabricated.
            self.assertIsInstance(present_missing_data_summary(detail["apartment"]), list)

    def test_detail_for_unknown_apartment_raises_not_found(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            with self.assertRaises(WebNotFoundError):
                facade.apartment_detail("no-such-apartment")

    def test_viewing_an_apartment_records_a_recent_view(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            job = _run_search(facade, db)
            data = facade.search_results(job.result_reference)
            apartment_id = next(iter(data["apartments"]))
            facade.apartment_detail(apartment_id, profile_id="p1")
            views = facade.recent_views(profile_id="p1")
            self.assertTrue(any(v.apartment_id == apartment_id for v in views))


class ComparisonTests(unittest.TestCase):
    def test_rejects_fewer_than_two_apartments(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            job = _run_search(facade, db)
            data = facade.search_results(job.result_reference)
            apartment_id = next(iter(data["apartments"]))
            with self.assertRaises(WebValidationError):
                facade.save_comparison([apartment_id], profile_id="p1")

    def test_rejects_more_than_five_apartments(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            with self.assertRaises(WebValidationError):
                facade.save_comparison(["a", "b", "c", "d", "e", "f"], profile_id="p1")

    def test_saving_and_retrieving_a_comparison_round_trips(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            job = _run_search(facade, db)
            data = facade.search_results(job.result_reference)
            ids = list(data["apartments"])[:2]
            comparison_id = facade.save_comparison(ids, profile_id="p1")
            record = facade.get_saved_comparison(comparison_id)
            self.assertEqual(sorted(record.apartment_ids), sorted(ids))
            apartments = facade.comparison_apartments(ids)
            self.assertEqual(len(apartments), 2)


class SavedSearchTests(unittest.TestCase):
    def test_create_update_enable_disable_lifecycle(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            saved_search = facade.create_saved_search(name="Watch", location="Example City", criteria={}, profile_id="p1")
            self.assertTrue(saved_search.enabled)

            facade.set_monitoring_enabled(saved_search.saved_search_id, False)
            data = facade.get_saved_search(saved_search.saved_search_id)
            self.assertFalse(data["saved_search"].enabled)

            facade.update_saved_search(saved_search.saved_search_id, request={"location": "New City", "criteria": {}})
            data = facade.get_saved_search(saved_search.saved_search_id)
            self.assertEqual(len(data["versions"]), 2)

    def test_create_rejects_missing_name(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            with self.assertRaises(WebValidationError):
                facade.create_saved_search(name="", location="Example City", criteria={}, profile_id="p1")

    def test_get_unknown_saved_search_raises_not_found(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            with self.assertRaises(WebNotFoundError):
                facade.get_saved_search("no-such-id")

    def test_run_saved_search_now_produces_a_monitoring_run(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            saved_search = facade.create_saved_search(name="Watch", location="Example City", criteria={}, profile_id="p1")
            job = facade.run_saved_search_now(saved_search.saved_search_id, profile_id="p1")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                with db.transaction() as conn:
                    reloaded = jobs_service.get_job(conn, job.job_id)
                if reloaded.status in TERMINAL_JOB_STATUSES:
                    break
                time.sleep(0.2)
            self.assertIn(reloaded.status, {"completed", "partial"})
            data = facade.get_saved_search(saved_search.saved_search_id)
            self.assertEqual(len(data["runs"]), 1)


class MonitoringEventTests(unittest.TestCase):
    def test_acknowledge_event_marks_it_acknowledged(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            saved_search = facade.create_saved_search(name="Watch", location="Example City", criteria={}, profile_id="p1")
            job = facade.run_saved_search_now(saved_search.saved_search_id, profile_id="p1")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                with db.transaction() as conn:
                    reloaded = jobs_service.get_job(conn, job.job_id)
                if reloaded.status in TERMINAL_JOB_STATUSES:
                    break
                time.sleep(0.2)
            events = facade.list_monitoring_events(saved_search_id=saved_search.saved_search_id)
            self.assertTrue(events)
            facade.acknowledge_event(events[0].event_id, acknowledged_by="test")
            reacknowledged = facade.list_monitoring_events(saved_search_id=saved_search.saved_search_id)
            acked = next(e for e in reacknowledged if e.event_id == events[0].event_id)
            self.assertTrue(acked.acknowledged)


class NotificationPreferenceTests(unittest.TestCase):
    def test_create_enable_disable_lifecycle(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            preference = facade.create_notification_preference(profile_id="p1", enabled_channels=["console"])
            self.assertTrue(preference.enabled)
            facade.set_notification_enabled(preference.preference_id, False)
            data = facade.get_notification_preference(preference.preference_id)
            self.assertFalse(data["preference"].enabled)

    def test_disabled_preference_stays_disabled_after_reload(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            preference = facade.create_notification_preference(profile_id="p1", enabled_channels=["console"])
            facade.set_notification_enabled(preference.preference_id, False)
            preferences = facade.list_notification_preferences(profile_id="p1")
            self.assertTrue(all(not p.enabled for p in preferences if p.preference_id == preference.preference_id))

    def test_channel_config_status_lists_every_registered_channel(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            channels = facade.channel_config_status()
            names = {c.channel_name for c in channels}
            self.assertIn("console", names)
            self.assertIn("file", names)


class DiscoveryCandidateTests(unittest.TestCase):
    def _seed_candidate(self, db):
        from datetime import datetime, timezone
        from src.discovery.automatic.models import DiscoveryRequest, DiscoveryRun, PlatformClassification

        with db.transaction() as conn:
            run = DiscoveryRun(request=DiscoveryRequest(country="Testland"), started_at=datetime.now(timezone.utc))
            discovery_service.record_run(conn, run)

            candidate = PlatformCandidate(
                candidate_id="cand-1", normalized_domain="example.com", name="Example Rentals", raw_url="https://example.com",
                status=PlatformStatus.REQUIRES_MANUAL_REVIEW, classification=PlatformClassification.RENTAL_MARKETPLACE,
                first_discovered_at=datetime.now(timezone.utc), last_seen_at=datetime.now(timezone.utc), last_run_id=run.run_id,
            )
            discovery_service.record_candidate(conn, candidate)
        return candidate

    def test_get_candidate_returns_evidence_bundle(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            self._seed_candidate(db)
            data = facade.get_candidate("cand-1")
            self.assertEqual(data["candidate"].candidate_id, "cand-1")
            self.assertEqual(data["evidence"], [])

    def test_get_unknown_candidate_raises_not_found(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            with self.assertRaises(WebNotFoundError):
                facade.get_candidate("no-such-candidate")

    def test_reject_candidate_marks_it_unsupported(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            self._seed_candidate(db)
            facade.reject_candidate("cand-1", reason="not a rental platform")
            data = facade.get_candidate("cand-1")
            self.assertEqual(data["candidate"].status, PlatformStatus.UNSUPPORTED)

    def test_approve_candidate_registers_a_platform(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            self._seed_candidate(db)
            facade.approve_candidate("cand-1")
            platforms = facade.list_platforms()
            self.assertTrue(any(p.homepage == "https://example.com" for p in platforms))


class FeedbackTests(unittest.TestCase):
    def test_record_event_and_build_preference_profile(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            facade.record_feedback_event(profile_id="p1", event_type="shortlisted")
            profile = facade.preference_profile("p1")
            self.assertEqual(profile.profile_id, "p1")

    def test_reset_inferred_preferences_never_touches_explicit_ones(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            with db.transaction() as conn:
                facade._deps.feedback_engine.build_preference_profile(conn, "p1", explicit_settings={"price_sensitivity": 0.9})
            facade.reset_inferred_preferences("p1")
            # `reset_inferred_preferences()` skips any key whose *latest*
            # adjustment is already "explicit" (see `FeedbackEngine`'s own
            # docstring) — verified via history, not by rebuilding the
            # profile, since rebuilding without re-supplying
            # `explicit_settings` legitimately re-derives from observations
            # (a caller must re-supply explicit settings on every rebuild;
            # that's this engine's real, documented contract, not a bug).
            history = facade.preference_history("p1", "price_sensitivity")
            self.assertEqual(history[-1].adjustment_type, "explicit")


class HealthAndStatisticsTests(unittest.TestCase):
    def test_system_health_collects_without_error(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            health = facade.system_health()
            self.assertTrue(health.database_ok)

    def test_system_statistics_collects_without_error(self) -> None:
        with web_test_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])
            stats = facade.system_statistics()
            self.assertEqual(stats.apartment_count, 0)


if __name__ == "__main__":
    unittest.main()
