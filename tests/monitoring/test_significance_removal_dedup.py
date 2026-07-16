"""Unit tests for the pure-function modules: significance scoring, the
listing-removal state machine, and event deduplication.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.monitoring import deduplication, removal, service, significance
from src.monitoring.models import MonitoringEvent, MonitoringPolicy
from src.storage.database import Database
from src.storage.models import MonitoringRunRecord, SavedSearchRecord
from src.storage import monitoring_repository

_NOW = datetime.now(timezone.utc)


class SignificanceTests(unittest.TestCase):
    def test_price_change_significance_is_a_fraction_of_old_price(self) -> None:
        self.assertAlmostEqual(significance.price_change_significance(1000, 900), 0.1)
        self.assertAlmostEqual(significance.price_change_significance(1000, 500), 0.5)

    def test_price_change_significance_caps_at_one(self) -> None:
        self.assertEqual(significance.price_change_significance(100, 1000), 1.0)

    def test_price_change_significance_zero_without_old_price(self) -> None:
        self.assertEqual(significance.price_change_significance(None, 500), 0.0)

    def test_availability_flip_scores_higher_than_non_flip(self) -> None:
        self.assertGreater(significance.availability_change_significance(True), significance.availability_change_significance(False))

    def test_new_listing_scores_higher_than_new_match(self) -> None:
        self.assertGreater(
            significance.new_match_significance(is_first_ever_listing=True),
            significance.new_match_significance(is_first_ever_listing=False),
        )

    def test_rank_change_significance_scales_with_total_candidates(self) -> None:
        self.assertGreater(significance.rank_change_significance(5, 10), significance.rank_change_significance(5, 100))

    def test_severity_thresholds(self) -> None:
        self.assertEqual(significance.severity_for_significance(0.9), "critical")
        self.assertEqual(significance.severity_for_significance(0.5), "warning")
        self.assertEqual(significance.severity_for_significance(0.1), "info")


class RemovalStateMachineTests(unittest.TestCase):
    def test_consecutive_absences_counts_until_first_presence(self) -> None:
        sets = [{"b"}, {"b"}, {"a", "b"}]  # newest-first; "a" present 2 runs ago
        self.assertEqual(removal.consecutive_absences(sets, "a"), 2)

    def test_consecutive_absences_zero_when_present_in_most_recent(self) -> None:
        sets = [{"a"}, {}]
        self.assertEqual(removal.consecutive_absences(sets, "a"), 0)

    def test_classify_missing_stages(self) -> None:
        policy = MonitoringPolicy(stale_listing_threshold=1, removed_listing_threshold=3)
        self.assertEqual(removal.classify_missing(0, policy), removal.PRESENT)
        self.assertEqual(removal.classify_missing(1, policy), removal.POSSIBLY_REMOVED)
        self.assertEqual(removal.classify_missing(2, policy), removal.POSSIBLY_REMOVED)
        self.assertEqual(removal.classify_missing(3, policy), removal.CONFIRMED_REMOVED)

    def test_does_not_mark_removed_after_a_single_miss(self) -> None:
        """"Do not mark a listing removed after one failed observation" (the
        mission's own words) — the default policy requires several consecutive
        misses before CONFIRMED_REMOVED.
        """
        policy = MonitoringPolicy()
        self.assertNotEqual(removal.classify_missing(1, policy), removal.CONFIRMED_REMOVED)

    def test_just_crossed_threshold_fires_exactly_once(self) -> None:
        policy = MonitoringPolicy(removed_listing_threshold=3)
        self.assertFalse(removal.just_crossed_removal_threshold(2, policy))
        self.assertTrue(removal.just_crossed_removal_threshold(3, policy))
        self.assertFalse(removal.just_crossed_removal_threshold(4, policy), "must not keep firing on every subsequent run")


class DeduplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            monitoring_repository.add_saved_search(conn, SavedSearchRecord(saved_search_id="s1", name="Test", current_version=1, enabled=True, created_at=_NOW, updated_at=_NOW))
            monitoring_repository.add_run(conn, MonitoringRunRecord(monitoring_run_id="r1", saved_search_id="s1", saved_search_version=1, status="running", started_at=_NOW, platforms_attempted=[], platforms_succeeded=[], platforms_failed=[]))

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _record(self, new_value: dict, detected_at: datetime) -> None:
        with self.db.transaction() as conn:
            service.record_event(conn, MonitoringEvent(
                saved_search_id="s1", saved_search_version=1, monitoring_run_id="r1", event_type="price_decreased",
                severity="info", significance=0.5, explanation="x", evidence={}, detected_at=detected_at,
                dedup_key="s1:apt1:price_decreased", new_value=new_value,
            ))

    def test_no_prior_event_is_not_a_duplicate(self) -> None:
        policy = MonitoringPolicy()
        with self.db.transaction() as conn:
            self.assertFalse(deduplication.is_duplicate(conn, "s1:apt1:price_decreased", {"price": 900}, policy, _NOW))

    def test_same_value_within_window_is_a_duplicate(self) -> None:
        self._record({"price": 900}, _NOW)
        policy = MonitoringPolicy(event_dedup_window_minutes=1440)
        with self.db.transaction() as conn:
            self.assertTrue(deduplication.is_duplicate(conn, "s1:apt1:price_decreased", {"price": 900}, policy, _NOW + timedelta(minutes=10)))

    def test_different_value_is_not_a_duplicate(self) -> None:
        self._record({"price": 900}, _NOW)
        policy = MonitoringPolicy(event_dedup_window_minutes=1440)
        with self.db.transaction() as conn:
            self.assertFalse(deduplication.is_duplicate(conn, "s1:apt1:price_decreased", {"price": 800}, policy, _NOW + timedelta(minutes=10)))

    def test_same_value_outside_window_is_not_a_duplicate(self) -> None:
        self._record({"price": 900}, _NOW)
        policy = MonitoringPolicy(event_dedup_window_minutes=60)
        with self.db.transaction() as conn:
            self.assertFalse(deduplication.is_duplicate(conn, "s1:apt1:price_decreased", {"price": 900}, policy, _NOW + timedelta(hours=2)))

    def test_make_dedup_key_is_stable_and_scoped(self) -> None:
        key_a = deduplication.make_dedup_key("s1", "apt1", "price_decreased")
        key_b = deduplication.make_dedup_key("s1", "apt1", "price_decreased")
        key_c = deduplication.make_dedup_key("s1", "apt2", "price_decreased")
        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)


if __name__ == "__main__":
    unittest.main()
