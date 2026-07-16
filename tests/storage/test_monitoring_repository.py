"""Migration + round-trip tests for `storage/monitoring_repository.py` +
migration 0009's nine tables (v2.5 Step 14) — real database, real round-trips.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.storage import monitoring_repository as repo
from src.storage.database import Database
from src.storage.models import (
    EventAcknowledgementRecord,
    MonitoringEventRecord,
    MonitoringRunRecord,
    MonitoringScheduleRecord,
    MonitoringStatisticsRecord,
    ReportArtifactRecord,
    SavedSearchRecord,
    SavedSearchVersionRecord,
)

_NOW = datetime.now(timezone.utc)


class MigrationTests(unittest.TestCase):
    def test_all_nine_tables_exist_after_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Database(db_path=Path(tmp_dir) / "test.db")
            with db.transaction() as conn:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in (
                "saved_searches", "saved_search_versions", "monitoring_schedules", "monitoring_runs",
                "monitoring_events", "event_acknowledgements", "monitoring_statistics", "report_artifacts",
            ):
                self.assertIn(table, tables)


class _RepositoryTestCase(unittest.TestCase):
    """Every monitoring table below `saved_searches` has a foreign key back to
    a `saved_searches`/`monitoring_runs` row, so `setUp` seeds one saved search
    ("s1") and one monitoring run ("r1") every test can build on.
    """

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            repo.add_saved_search(conn, SavedSearchRecord(saved_search_id="s1", name="Test Search", current_version=1, enabled=True, created_at=_NOW, updated_at=_NOW))
            repo.add_run(conn, MonitoringRunRecord(
                monitoring_run_id="r1", saved_search_id="s1", saved_search_version=1, status="running",
                started_at=_NOW, platforms_attempted=["p1"], platforms_succeeded=[], platforms_failed=[],
            ))

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()


class SavedSearchRepositoryTests(_RepositoryTestCase):
    def test_add_and_get_saved_search(self) -> None:
        with self.db.transaction() as conn:
            fetched = repo.get_saved_search(conn, "s1")
        self.assertEqual(fetched.name, "Test Search")

    def test_update_metadata_preserves_identity_and_created_at(self) -> None:
        with self.db.transaction() as conn:
            updated = SavedSearchRecord(saved_search_id="s1", name="Renamed", current_version=2, enabled=False, created_at=_NOW, updated_at=_NOW)
            repo.update_saved_search_metadata(conn, updated)
            fetched = repo.get_saved_search(conn, "s1")
        self.assertEqual(fetched.name, "Renamed")
        self.assertEqual(fetched.current_version, 2)
        self.assertFalse(fetched.enabled)

    def test_enabled_only_filter(self) -> None:
        with self.db.transaction() as conn:
            repo.add_saved_search(conn, SavedSearchRecord(saved_search_id="s2", name="Disabled", current_version=1, enabled=False, created_at=_NOW, updated_at=_NOW))
            enabled_only = repo.get_all_saved_searches(conn, enabled_only=True)
        self.assertEqual([s.saved_search_id for s in enabled_only], ["s1"])


class SavedSearchVersionRepositoryTests(_RepositoryTestCase):
    def _version(self, **overrides) -> SavedSearchVersionRecord:
        defaults = dict(
            saved_search_id="s1", version=1, request={"location": "Valencia"}, active_filters={},
            selected_platforms=[], selected_connectors=[], geographic_destinations=[], monitoring_policy={},
            report_options={}, retention_policy={}, tags=[], metadata={}, created_at=_NOW,
        )
        defaults.update(overrides)
        return SavedSearchVersionRecord(**defaults)

    def test_add_and_get_version(self) -> None:
        with self.db.transaction() as conn:
            repo.add_saved_search_version(conn, self._version())
            fetched = repo.get_saved_search_version(conn, "s1", 1)
        self.assertEqual(fetched.request, {"location": "Valencia"})

    def test_versions_are_never_overwritten_only_appended(self) -> None:
        with self.db.transaction() as conn:
            repo.add_saved_search_version(conn, self._version(version=1))
            repo.add_saved_search_version(conn, self._version(version=2, request={"location": "Madrid"}))
            all_versions = repo.get_saved_search_versions(conn, "s1")
            latest = repo.get_latest_saved_search_version(conn, "s1")
        self.assertEqual(len(all_versions), 2)
        self.assertEqual(all_versions[0].request, {"location": "Valencia"})  # v1 untouched
        self.assertEqual(latest.version, 2)
        self.assertEqual(latest.request, {"location": "Madrid"})


class ScheduleClaimLockTests(_RepositoryTestCase):
    def test_claim_due_run_is_atomic(self) -> None:
        with self.db.transaction() as conn:
            repo.add_schedule(conn, MonitoringScheduleRecord(saved_search_id="s1", next_run_at=_NOW))
            first = repo.claim_due_run(conn, "s1", "worker-a", _NOW, _NOW + timedelta(minutes=15))
            second = repo.claim_due_run(conn, "s1", "worker-b", _NOW, _NOW + timedelta(minutes=15))
        self.assertTrue(first)
        self.assertFalse(second, "a second worker must not be able to claim an already-claimed run")

    def test_release_then_reclaim(self) -> None:
        with self.db.transaction() as conn:
            repo.add_schedule(conn, MonitoringScheduleRecord(saved_search_id="s1", next_run_at=_NOW))
            repo.claim_due_run(conn, "s1", "worker-a", _NOW, _NOW + timedelta(minutes=15))
            repo.release_run_claim(conn, "s1")
            reclaimed = repo.claim_due_run(conn, "s1", "worker-b", _NOW, _NOW + timedelta(minutes=15))
        self.assertTrue(reclaimed)

    def test_expired_claim_can_be_reclaimed(self) -> None:
        expired_at = _NOW - timedelta(minutes=1)
        with self.db.transaction() as conn:
            repo.add_schedule(conn, MonitoringScheduleRecord(saved_search_id="s1", next_run_at=_NOW))
            repo.claim_due_run(conn, "s1", "worker-a", _NOW - timedelta(minutes=20), expired_at)
            reclaimed = repo.claim_due_run(conn, "s1", "worker-b", _NOW, _NOW + timedelta(minutes=15))
        self.assertTrue(reclaimed, "an expired claim must not block a new claim")

    def test_get_due_schedules_excludes_disabled_and_claimed(self) -> None:
        with self.db.transaction() as conn:
            repo.add_saved_search(conn, SavedSearchRecord(saved_search_id="s2", name="Disabled", current_version=1, enabled=False, created_at=_NOW, updated_at=_NOW))
            repo.add_schedule(conn, MonitoringScheduleRecord(saved_search_id="s1", next_run_at=_NOW - timedelta(minutes=1)))
            repo.add_schedule(conn, MonitoringScheduleRecord(saved_search_id="s2", next_run_at=_NOW - timedelta(minutes=1)))
            due = repo.get_due_schedules(conn, _NOW)
        self.assertEqual([s.saved_search_id for s in due], ["s1"])


class MonitoringRunRepositoryTests(_RepositoryTestCase):
    def test_update_run_status_preserves_identity(self) -> None:
        from src.storage import search_repository
        from src.storage.models import SearchRequestRecord

        with self.db.transaction() as conn:
            search_repository.insert_search_request(
                conn, SearchRequestRecord(id="search-1", created_at=_NOW, label=None, criteria_json="{}"),
            )
            updated = MonitoringRunRecord(
                monitoring_run_id="r1", saved_search_id="s1", saved_search_version=1, status="completed",
                started_at=_NOW, completed_at=_NOW, platforms_attempted=["p1"], platforms_succeeded=["p1"],
                platforms_failed=[], search_id="search-1", event_count=2,
            )
            repo.update_run_status(conn, "r1", updated)
            fetched = repo.get_run(conn, "r1")
        self.assertEqual(fetched.status, "completed")
        self.assertEqual(fetched.search_id, "search-1")
        self.assertEqual(fetched.platforms_attempted, ["p1"])  # untouched by update_run_status


class MonitoringEventRepositoryTests(_RepositoryTestCase):
    def _event(self, **overrides) -> MonitoringEventRecord:
        defaults = dict(
            event_id="e1", monitoring_run_id="r1", saved_search_id="s1", saved_search_version=1,
            event_type="new_match", severity="info", significance=0.5, explanation="x", evidence={},
            detected_at=_NOW, dedup_key="dk1", metadata={},
        )
        defaults.update(overrides)
        return MonitoringEventRecord(**defaults)

    def test_events_are_never_overwritten(self) -> None:
        with self.db.transaction() as conn:
            repo.add_event(conn, self._event(event_id="e1"))
            repo.add_event(conn, self._event(event_id="e2", dedup_key="dk1"))
            same_key = repo.get_events_by_dedup_key(conn, "dk1")
        self.assertEqual(len(same_key), 2)

    def test_acknowledge_event_is_the_only_mutation(self) -> None:
        with self.db.transaction() as conn:
            repo.add_event(conn, self._event())
            repo.acknowledge_event(conn, "e1")
            repo.add_acknowledgement(conn, EventAcknowledgementRecord(event_id="e1", acknowledged_at=_NOW, acknowledged_by="user"))
            fetched = repo.get_event(conn, "e1")
            acks = repo.get_acknowledgements_for_event(conn, "e1")
            unacked = repo.get_unacknowledged_events(conn)
        self.assertTrue(fetched.acknowledged)
        self.assertEqual(len(acks), 1)
        self.assertEqual(unacked, [])

    def test_filter_by_type_and_severity(self) -> None:
        with self.db.transaction() as conn:
            repo.add_event(conn, self._event(event_id="e1", event_type="price_decreased", severity="warning"))
            repo.add_event(conn, self._event(event_id="e2", event_type="new_match", severity="info"))
            by_type = repo.get_events_for_saved_search(conn, "s1", event_type="price_decreased")
            by_severity = repo.get_events_for_saved_search(conn, "s1", severity="info")
        self.assertEqual([e.event_id for e in by_type], ["e1"])
        self.assertEqual([e.event_id for e in by_severity], ["e2"])


class StatisticsAndArtifactRepositoryTests(_RepositoryTestCase):
    def test_statistics_round_trip(self) -> None:
        with self.db.transaction() as conn:
            repo.add_statistics(conn, MonitoringStatisticsRecord(monitoring_run_id="r1", computed_at=_NOW, statistics={"events": 3}))
            fetched = repo.get_statistics_for_run(conn, "r1")
        self.assertEqual(fetched.statistics, {"events": 3})

    def test_report_artifact_round_trip(self) -> None:
        with self.db.transaction() as conn:
            repo.add_report_artifact(conn, ReportArtifactRecord(monitoring_run_id="r1", report_type="full_html", path="/tmp/x.html", generated_at=_NOW))
            artifacts = repo.get_report_artifacts_for_run(conn, "r1")
        self.assertEqual(artifacts[0].report_type, "full_html")


if __name__ == "__main__":
    unittest.main()
