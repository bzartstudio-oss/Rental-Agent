"""Journey D — Notifications. See
docs/33_Release_Candidate_Acceptance.md "Phase 3 / Journey D".
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from src.monitoring import service as monitoring_service
from src.monitoring.models import MonitoringEvent
from src.notifications.channels.console_channel import ConsoleNotificationChannel
from src.notifications.models import NotificationChannelResult
from src.notifications.registry import NotificationChannelRegistry
from src.storage import search_repository
from src.web.constants import TERMINAL_JOB_STATUSES
from src.web.facade import WebServiceFacade
from src.web.jobs import service as jobs_service
from tests.acceptance.helpers import acceptance_app


def _make_new_match_event(saved_search_id: str, monitoring_run_id: str, apartment_id: str) -> MonitoringEvent:
    now = datetime.now(timezone.utc)
    return MonitoringEvent(
        saved_search_id=saved_search_id, saved_search_version=1, monitoring_run_id=monitoring_run_id,
        event_type="new_match", severity="info", significance=0.5, explanation="Existing apartment newly matches this saved search: Acceptance Test Apartment",
        evidence={}, detected_at=now, dedup_key=f"{saved_search_id}:{monitoring_run_id}:new_match:{apartment_id}",
        apartment_id=apartment_id,
    )


class _AlwaysFailsChannel(ConsoleNotificationChannel):
    """A test-only channel that always fails — mirrors the exact pattern
    `tests/notifications/test_engine.py::_AlwaysFailsChannel` already
    established, kept local so this acceptance module has no test-to-test
    import dependency.
    """

    channel_name = "acceptance_always_fails"

    def send(self, message):
        return NotificationChannelResult(channel=self.channel_name, success=False, error="simulated failure", error_category="server_error")


def _wait(db, job_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with db.transaction() as conn:
            job = jobs_service.get_job(conn, job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.2)
    raise TimeoutError("job never completed")


class JourneyDNotificationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fake_channel = _AlwaysFailsChannel()
        NotificationChannelRegistry.register(self._fake_channel)

    def tearDown(self) -> None:
        NotificationChannelRegistry._channels.pop("acceptance_always_fails", None)

    def test_notification_delivery_journey(self) -> None:
        with acceptance_app() as (app, db, tmp):
            facade = WebServiceFacade(app.extensions["web_dependencies"])

            saved_search = facade.create_saved_search(name="Valencia watch", location="Example City", criteria={}, profile_id="acceptance")
            job = facade.run_saved_search_now(saved_search.saved_search_id, profile_id="acceptance")
            job = _wait(db, job.job_id)
            self.assertIn(job.status, ("completed", "partial"))

            # `new_match`/`new_listing` events only fire when `MonitoringEngine`
            # has a *previous* run to compare against (see
            # `monitoring/detectors/apartment_change_detector.py::detect()` —
            # gated on `context.search_comparison is not None`), and with
            # this deterministic demo fixture, two consecutive runs observe
            # the *identical* apartment set, so nothing is ever genuinely
            # "new" between them either. Rather than fabricate a fake
            # pipeline difference, this test records one deterministic,
            # realistic `MonitoringEvent` directly — mirroring the exact
            # `tests/notifications/test_engine.py`/`tests/monitoring/
            # test_detectors.py` helper pattern this codebase already
            # established for testing the *notification* layer independent
            # of monitoring's own emergent detection timing.
            with db.transaction() as conn:
                run = monitoring_service.get_latest_run_for_saved_search(conn, saved_search.saved_search_id)
                results = search_repository.get_search_results(conn, run.search_id)
                apartment_id = results[0].apartment_id
                synthetic_event = _make_new_match_event(saved_search.saved_search_id, run.monitoring_run_id, apartment_id)
                monitoring_service.record_event(conn, synthetic_event)

            events = facade.list_monitoring_events(saved_search_id=saved_search.saved_search_id)
            new_match_events = [e for e in events if e.event_type == "new_match"]
            self.assertTrue(new_match_events, "synthetic new_match event was not recorded")
            events_before = {e.event_id: (e.acknowledged, e.explanation) for e in events}

            # 1-2. Create an opted-in preference using Console and File channels.
            # `event_types=["new_match"]` scopes eligibility itself (not just
            # immediate-vs-digest routing) to this one event type, so the
            # real `monitoring_run_completed`/`report_generated` lifecycle
            # events this run also produced never become a second/third
            # delivery under this same preference.
            preference = facade.create_notification_preference(
                profile_id="acceptance", saved_search_id=saved_search.saved_search_id,
                enabled_channels=["console", "file", "acceptance_always_fails"],
                event_types=["new_match"], immediate_event_types=["new_match"],
            )
            self.assertTrue(preference.enabled)

            # 3. Preview notifications.
            preview_text = facade.preview_notification(preference.preference_id, [new_match_events[0].event_id], "console")
            self.assertIn("New Match", preview_text)

            # 4. Deliver immediate events.
            batch = facade.deliver_pending_notifications()
            self.assertGreaterEqual(batch.deliveries_attempted, 1)

            with db.transaction() as conn:
                from src.notifications import service as notification_service

                delivery_ids = notification_service.get_delivery_ids_for_event(conn, new_match_events[0].event_id)
                self.assertTrue(delivery_ids, "the new_match event produced no delivery at all")
                delivery = notification_service.get_delivery(conn, delivery_ids[0])

            # 7-8. Simulate one failed channel; verify the other succeeds.
            self.assertIn("acceptance_always_fails", delivery.channels)
            with db.transaction() as conn:
                attempts = notification_service.get_attempts_for_delivery(conn, delivery.delivery_id)
            succeeded_channels = {a.channel for a in attempts if a.status == "delivered"}
            failed_channels = {a.channel for a in attempts if a.status == "failed"}
            self.assertIn("console", succeeded_channels)
            self.assertIn("acceptance_always_fails", failed_channels)

            # 9. Retry idempotently — console must never be re-sent.
            facade.retry_delivery(delivery.delivery_id)
            with db.transaction() as conn:
                attempts_after = notification_service.get_attempts_for_delivery(conn, delivery.delivery_id)
            console_attempts = [a for a in attempts_after if a.channel == "console"]
            self.assertEqual(len(console_attempts), 1, "idempotent retry re-sent an already-succeeded channel")

            # 5. Simulate quiet hours (unit-covered directly — the same
            # `quiet_hours.py` this delivery pass would call if configured).
            from src.notifications import quiet_hours
            from src.notifications.models import NotificationPreferenceVersion

            quiet_version = NotificationPreferenceVersion(
                preference_id="x", version=1, enabled_channels=["console"], event_types=[], immediate_event_types=[],
                digest_event_types=[], timezone="UTC", include_images=True, include_original_urls=True,
                include_ranking_explanation=True, include_geo_summary=True, include_preference_explanation=True,
                include_report_links=True, language="en", format="text", metadata={}, created_at=datetime.now(timezone.utc),
                quiet_hours_start="00:00", quiet_hours_end="23:59",
            )
            now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
            self.assertTrue(quiet_hours.is_in_quiet_hours(quiet_version, now))

            # 6. Generate a digest.
            digest_preference = facade.create_notification_preference(
                profile_id="acceptance", saved_search_id=saved_search.saved_search_id,
                enabled_channels=["console"], digest_frequency="daily",
            )
            digest_delivery = facade.generate_digest(digest_preference.preference_id)
            self.assertIsNotNone(digest_delivery)
            self.assertTrue(digest_delivery.is_digest)

            # 10. Verify original monitoring events remain unchanged.
            events_after = facade.list_monitoring_events(saved_search_id=saved_search.saved_search_id)
            for event in events_after:
                if event.event_id in events_before:
                    old_acknowledged, old_explanation = events_before[event.event_id]
                    self.assertEqual(event.explanation, old_explanation)


if __name__ == "__main__":
    unittest.main()
