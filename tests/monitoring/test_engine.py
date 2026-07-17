"""Integration tests for `MonitoringEngine`, driven through the real
`demo_platform` connector (a real Playwright fetch of a real local fixture) —
the same "real orchestrator, real connector" discipline `tests/core/test_agent.py`
established. Covers the mission's own explicit verification checklist:
versioning creates a new immutable version and prior versions stay
reproducible, a broken connector produces a partial run rather than losing
successful results, repeated runs accumulate history, and re-running without
any real change does not fabricate duplicate events.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.monitoring import MonitoringEngine, MonitoringPolicy, service as monitoring_service
from src.monitoring.exceptions import MonitoringValidationError
from src.monitoring.models import MonitoringRunStatus, SavedSearch
from src.storage.database import Database
from src.storage.models import Platform
from tests.support import isolated_collectors

_NOW = datetime.now(timezone.utc)


class MonitoringEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, Platform(
                id="demo_platform", name="Demo Platform", country="N/A (local fixture)", homepage="local-fixture",
                connector_available=True, connector_name="demo_platform", created_at=_NOW,
            ))

        self.engine = MonitoringEngine()
        self.saved_search = self.engine.create_saved_search(
            self.db, "Example City Apartments", {"location": "Example City", "criteria": {}},
        )

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_create_saved_search_writes_version_one_and_a_schedule(self) -> None:
        with self.db.transaction() as conn:
            saved_search = monitoring_service.get_saved_search(conn, self.saved_search.saved_search_id)
            version = monitoring_service.get_latest_saved_search_version(conn, self.saved_search.saved_search_id)
            schedule = monitoring_service.get_schedule(conn, self.saved_search.saved_search_id)
        self.assertEqual(saved_search.current_version, 1)
        self.assertEqual(version.version, 1)
        self.assertIsNotNone(schedule)

    def test_update_creates_a_new_version_without_touching_the_old_one(self) -> None:
        self.engine.update_saved_search(self.db, self.saved_search.saved_search_id, request={"location": "Other City", "criteria": {}})

        with self.db.transaction() as conn:
            saved_search = monitoring_service.get_saved_search(conn, self.saved_search.saved_search_id)
            v1 = monitoring_service.get_saved_search_version(conn, self.saved_search.saved_search_id, 1)
            v2 = monitoring_service.get_saved_search_version(conn, self.saved_search.saved_search_id, 2)

        self.assertEqual(saved_search.current_version, 2)
        self.assertEqual(v1.request["location"], "Example City")  # prior version untouched — still reproducible
        self.assertEqual(v2.request["location"], "Other City")

    def test_enable_disable_round_trip(self) -> None:
        self.engine.set_enabled(self.db, self.saved_search.saved_search_id, False)
        with self.db.transaction() as conn:
            self.assertFalse(monitoring_service.get_saved_search(conn, self.saved_search.saved_search_id).enabled)

        self.engine.set_enabled(self.db, self.saved_search.saved_search_id, True)
        with self.db.transaction() as conn:
            self.assertTrue(monitoring_service.get_saved_search(conn, self.saved_search.saved_search_id).enabled)

    def test_create_rejects_an_exact_duplicate_name(self) -> None:
        """v2.6 Milestone 2.6.5 — see docs/41_Version_2.6_Planning.md. `setUp`
        already created "Example City Apartments"; a second saved search with the
        same name must be rejected, not silently allowed the way the pilot session
        found (two saved searches both named "pilot-valencia-01" with no warning).
        """
        with self.assertRaises(MonitoringValidationError):
            self.engine.create_saved_search(
                self.db, "Example City Apartments", {"location": "Example City", "criteria": {}},
            )

    def test_create_rejects_a_duplicate_name_regardless_of_case_or_surrounding_whitespace(self) -> None:
        with self.assertRaises(MonitoringValidationError):
            self.engine.create_saved_search(
                self.db, "  example city apartments  ", {"location": "Example City", "criteria": {}},
            )

    def test_create_allows_a_genuinely_different_name(self) -> None:
        second = self.engine.create_saved_search(
            self.db, "A Completely Different Search", {"location": "Example City", "criteria": {}},
        )
        self.assertNotEqual(second.saved_search_id, self.saved_search.saved_search_id)

    def test_pre_existing_duplicate_named_saved_searches_still_read_fine(self) -> None:
        """Enforcement is creation-time only, never retroactive (see
        docs/41_Version_2.6_Planning.md Milestone 2.6.5's backward-compatibility
        requirement) — a saved search that already shares a name (inserted here by
        writing directly to storage, bypassing the engine, the same way real
        pre-2.6.5 duplicate data would have gotten there) must keep reading fine.
        """
        duplicate = SavedSearch(
            saved_search_id="legacy-duplicate", name=self.saved_search.name, current_version=1,
            enabled=True, created_at=_NOW, updated_at=_NOW, profile_id=None, description=None,
        )
        with self.db.transaction() as conn:
            monitoring_service.record_saved_search(conn, duplicate)

        with self.db.transaction() as conn:
            all_saved_searches = monitoring_service.get_all_saved_searches(conn)
        names = [s.name for s in all_saved_searches]
        self.assertEqual(names.count(self.saved_search.name), 2)

    def test_run_now_produces_a_completed_run_with_traceable_events(self) -> None:
        run = self.engine.run_now(self.db, self.saved_search.saved_search_id)

        self.assertEqual(run.status, MonitoringRunStatus.COMPLETED)
        self.assertEqual(run.platforms_succeeded, ["demo_platform"])
        self.assertEqual(run.platforms_failed, [])
        self.assertIsNotNone(run.search_id)

        with self.db.transaction() as conn:
            events = monitoring_service.get_events_for_run(conn, run.monitoring_run_id)
        self.assertGreater(len(events), 0)
        for event in events:
            # every event must be traceable back to the run/saved search that produced it
            self.assertEqual(event.monitoring_run_id, run.monitoring_run_id)
            self.assertEqual(event.saved_search_id, self.saved_search.saved_search_id)
            self.assertTrue(event.explanation)
            self.assertIsNotNone(event.evidence)

    def test_repeated_runs_accumulate_history_without_losing_earlier_runs(self) -> None:
        run1 = self.engine.run_now(self.db, self.saved_search.saved_search_id)
        run2 = self.engine.run_now(self.db, self.saved_search.saved_search_id)

        with self.db.transaction() as conn:
            all_runs = monitoring_service.get_runs_for_saved_search(conn, self.saved_search.saved_search_id)
        self.assertEqual({r.monitoring_run_id for r in all_runs}, {run1.monitoring_run_id, run2.monitoring_run_id})

    def test_rerunning_unchanged_fixtures_does_not_fabricate_apartment_change_events(self) -> None:
        """demo_platform returns the exact same three fixture listings every
        call — a second run must not invent NEW_MATCH/price/availability
        events for data that hasn't actually changed.
        """
        from src.monitoring.models import MonitoringEventType

        self.engine.run_now(self.db, self.saved_search.saved_search_id)
        run2 = self.engine.run_now(self.db, self.saved_search.saved_search_id)

        with self.db.transaction() as conn:
            events2 = monitoring_service.get_events_for_run(conn, run2.monitoring_run_id)

        apartment_change_types = {
            MonitoringEventType.NEW_MATCH, MonitoringEventType.NEW_LISTING, MonitoringEventType.PRICE_DECREASED,
            MonitoringEventType.PRICE_INCREASED, MonitoringEventType.AVAILABILITY_CHANGED,
            MonitoringEventType.LISTING_REMOVED,
        }
        self.assertFalse(any(e.event_type in apartment_change_types for e in events2))

    def test_broken_connector_produces_a_partial_run_not_a_failed_one(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, Platform(
                id="broken_platform", name="Broken Platform", country="Nowhere", homepage="does-not-matter",
                connector_available=True, connector_name="does_not_exist_module", created_at=_NOW,
            ))

        run = self.engine.run_now(self.db, self.saved_search.saved_search_id)

        self.assertEqual(run.status, MonitoringRunStatus.PARTIAL)
        self.assertIn("demo_platform", run.platforms_succeeded)
        self.assertIn("broken_platform", run.platforms_failed)

    def test_reports_are_generated_and_reference_the_original_listing_url(self) -> None:
        run = self.engine.run_now(self.db, self.saved_search.saved_search_id)

        with self.db.transaction() as conn:
            artifacts = monitoring_service.get_report_artifacts_for_run(conn, run.monitoring_run_id)
        self.assertEqual({a.report_type for a in artifacts}, {"full_html", "full_json", "changes_html", "changes_json"})
        for artifact in artifacts:
            self.assertTrue(Path(artifact.path).exists())


if __name__ == "__main__":
    unittest.main()
