"""Unit tests for each built-in `EventDetector`, driven directly against a
hand-built `MonitoringDetectionContext` — no full `RentalResearchAgent` run
needed, since each detector only reads already-computed evidence (a
`SearchComparison`, persisted `search_results`, prior observed-apartment
sets). See tests/monitoring/test_engine.py for the full pipeline wired
end-to-end through a real connector.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.monitoring.base_detector import MonitoringDetectionContext
from src.monitoring.detectors.apartment_change_detector import ApartmentChangeDetector
from src.monitoring.detectors.discovery_detector import DiscoveryDetector
from src.monitoring.detectors.filter_match_detector import FilterMatchDetector
from src.monitoring.detectors.platform_health_detector import PlatformHealthDetector
from src.monitoring.detectors.ranking_change_detector import RankingChangeDetector
from src.monitoring.models import (
    MonitoringEventType,
    MonitoringPolicy,
    MonitoringRun,
    MonitoringRunStatus,
    SavedSearch,
    SavedSearchVersion,
)
from src.search_memory.models import ApartmentAvailabilityChange, ApartmentPriceChange, PlatformCoverageChange, SearchComparison
from src.storage import apartment_repository
from src.storage.database import Database
from src.storage.models import Apartment, Platform, SearchResultEntry

_NOW = datetime.now(timezone.utc)


class _DetectorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            platform_registry.register_platform(conn, Platform(
                id="p1", name="Platform 1", country="Spain", homepage="https://p1.example", connector_available=True,
                connector_name="p1", created_at=_NOW,
            ))

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _insert_apartment(self, conn, apartment_id: str, *, first_seen_at=_NOW, last_seen_at=_NOW, price=1000.0, status="available", title="Test Apartment") -> None:
        apartment_repository.insert_apartment(conn, Apartment(
            id=apartment_id, platform_id="p1", platform_listing_id=apartment_id, title=title, url=f"https://p1.example/{apartment_id}",
            current_price=price, current_status=status, first_seen_at=first_seen_at, last_seen_at=last_seen_at,
        ))

    def _context(self, conn, **overrides) -> MonitoringDetectionContext:
        saved_search = SavedSearch(saved_search_id="s1", name="Test", current_version=1, enabled=True, created_at=_NOW, updated_at=_NOW)
        version = SavedSearchVersion(
            saved_search_id="s1", version=1, request={"location": "Valencia"}, active_filters={}, selected_platforms=[],
            selected_connectors=[], geographic_destinations=[], monitoring_policy=overrides.pop("policy", MonitoringPolicy()),
            report_options={}, retention_policy={}, tags=[], metadata={}, created_at=_NOW,
        )
        run = MonitoringRun(saved_search_id="s1", saved_search_version=1, started_at=_NOW, status=MonitoringRunStatus.RUNNING, monitoring_run_id="r-current")
        defaults = dict(
            conn=conn, saved_search=saved_search, version=version, run=run, policy=version.monitoring_policy, now=_NOW,
            previous_run=None, search_comparison=None, current_search_results=[], previous_search_results=[],
            discovery_comparison=None, current_observed_apartment_ids=set(), prior_observed_apartment_sets=[],
        )
        defaults.update(overrides)
        return MonitoringDetectionContext(**defaults)

    def _empty_comparison(self, **overrides) -> SearchComparison:
        defaults = dict(
            previous_search_id="prev", current_search_id="curr", new_apartment_ids=[], removed_apartment_ids=[],
            changed_apartment_ids=[], price_changes=[], availability_changes=[], connector_failures=[],
            platform_coverage_change=PlatformCoverageChange(newly_searched_platform_ids=[], no_longer_searched_platform_ids=[]),
            execution_time_delta_ms=None, search_quality_delta=None,
        )
        defaults.update(overrides)
        return SearchComparison(**defaults)


class ApartmentChangeDetectorNewMatchTests(_DetectorTestCase):
    def test_never_seen_before_is_a_new_listing(self) -> None:
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", first_seen_at=_NOW, last_seen_at=_NOW)
            context = self._context(
                conn, search_comparison=self._empty_comparison(new_apartment_ids=["apt1"]),
                current_observed_apartment_ids={"apt1"},
            )
            events = ApartmentChangeDetector().detect(context)
        types = [e.event_type for e in events]
        self.assertIn(MonitoringEventType.NEW_LISTING, types)
        self.assertNotIn(MonitoringEventType.NEW_MATCH, types)

    def test_brand_new_apartment_with_prior_run_history_is_still_new_not_returned(self) -> None:
        """Regression test: a brand-new apartment (never observed in ANY prior
        run) must not be misclassified as LISTING_RETURNED just because it's
        absent from every set in `prior_observed_apartment_sets` — absent from
        *every* set (a full scan with no match) means "never seen," not "seen,
        then missing." Caught during the Step 14 Valencia live demonstration:
        `consecutive_absences()` returning `len(prior_observed_apartment_sets)`
        (exhausted the whole scan without finding it) was being treated the
        same as returning a smaller, genuine miss count.
        """
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", first_seen_at=_NOW, last_seen_at=_NOW)
            context = self._context(
                conn, search_comparison=self._empty_comparison(new_apartment_ids=["apt1"]),
                current_observed_apartment_ids={"apt1"},
                prior_observed_apartment_sets=[{"other_apt"}, {"other_apt"}],  # apt1 never appears
            )
            events = ApartmentChangeDetector().detect(context)
        types = [e.event_type for e in events]
        self.assertIn(MonitoringEventType.NEW_LISTING, types)
        self.assertNotIn(MonitoringEventType.LISTING_RETURNED, types)

    def test_previously_seen_apartment_newly_matching_is_a_new_match(self) -> None:
        from datetime import timedelta
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", first_seen_at=_NOW - timedelta(days=5), last_seen_at=_NOW)
            context = self._context(
                conn, search_comparison=self._empty_comparison(new_apartment_ids=["apt1"]),
                current_observed_apartment_ids={"apt1"},
            )
            events = ApartmentChangeDetector().detect(context)
        types = [e.event_type for e in events]
        self.assertIn(MonitoringEventType.NEW_MATCH, types)
        self.assertNotIn(MonitoringEventType.NEW_LISTING, types)


class ApartmentChangeDetectorPriceTests(_DetectorTestCase):
    def test_price_decrease_event(self) -> None:
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", price=800.0)
            comparison = self._empty_comparison(price_changes=[ApartmentPriceChange(apartment_id="apt1", old_price=1000.0, new_price=800.0)])
            context = self._context(conn, search_comparison=comparison, current_observed_apartment_ids={"apt1"})
            events = ApartmentChangeDetector().detect(context)
        price_events = [e for e in events if e.event_type == MonitoringEventType.PRICE_DECREASED]
        self.assertEqual(len(price_events), 1)
        self.assertEqual(price_events[0].old_value, {"price": 1000.0})
        self.assertEqual(price_events[0].new_value, {"price": 800.0})

    def test_price_increase_event(self) -> None:
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", price=1200.0)
            comparison = self._empty_comparison(price_changes=[ApartmentPriceChange(apartment_id="apt1", old_price=1000.0, new_price=1200.0)])
            context = self._context(conn, search_comparison=comparison, current_observed_apartment_ids={"apt1"})
            events = ApartmentChangeDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.PRICE_INCREASED for e in events))

    def test_price_change_below_minimum_significance_is_suppressed(self) -> None:
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", price=999.0)
            comparison = self._empty_comparison(price_changes=[ApartmentPriceChange(apartment_id="apt1", old_price=1000.0, new_price=999.0)])
            policy = MonitoringPolicy(minimum_change_significance=0.5)  # a 0.1% drop won't clear this
            context = self._context(conn, search_comparison=comparison, current_observed_apartment_ids={"apt1"}, policy=policy)
            events = ApartmentChangeDetector().detect(context)
        self.assertFalse(any(e.event_type in (MonitoringEventType.PRICE_DECREASED, MonitoringEventType.PRICE_INCREASED) for e in events))


class ApartmentChangeDetectorAvailabilityTests(_DetectorTestCase):
    def test_became_available_event(self) -> None:
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", status="available")
            comparison = self._empty_comparison(availability_changes=[ApartmentAvailabilityChange(apartment_id="apt1", old_status="rented", new_status="available")])
            context = self._context(conn, search_comparison=comparison, current_observed_apartment_ids={"apt1"})
            events = ApartmentChangeDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.BECAME_AVAILABLE for e in events))

    def test_no_longer_available_event(self) -> None:
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", status="rented")
            comparison = self._empty_comparison(availability_changes=[ApartmentAvailabilityChange(apartment_id="apt1", old_status="available", new_status="rented")])
            context = self._context(conn, search_comparison=comparison, current_observed_apartment_ids={"apt1"})
            events = ApartmentChangeDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.NO_LONGER_AVAILABLE for e in events))


class ApartmentChangeDetectorRemovalTests(_DetectorTestCase):
    def test_single_miss_does_not_confirm_removal(self) -> None:
        """"Do not mark a listing removed after one failed observation." """
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1")
            context = self._context(
                conn, current_observed_apartment_ids=set(),  # apt1 absent this run
                prior_observed_apartment_sets=[{"apt1"}],  # present in the one prior run
            )
            events = ApartmentChangeDetector().detect(context)
        self.assertFalse(any(e.event_type == MonitoringEventType.LISTING_REMOVED for e in events))

    def test_removal_confirmed_exactly_at_threshold(self) -> None:
        policy = MonitoringPolicy(removed_listing_threshold=3, stale_listing_threshold=1)
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1")
            # 2 prior misses + this run's own absence = 3 consecutive misses, exactly at threshold.
            context = self._context(
                conn, current_observed_apartment_ids=set(), prior_observed_apartment_sets=[set(), set(), {"apt1"}],
                policy=policy,
            )
            events = ApartmentChangeDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.LISTING_REMOVED for e in events))

    def test_removal_event_does_not_repeat_every_subsequent_run(self) -> None:
        policy = MonitoringPolicy(removed_listing_threshold=3, stale_listing_threshold=1)
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1")
            # 3 prior misses + this run = 4 consecutive misses -- past the threshold, not exactly at it.
            context = self._context(
                conn, current_observed_apartment_ids=set(), prior_observed_apartment_sets=[set(), set(), set(), {"apt1"}],
                policy=policy,
            )
            events = ApartmentChangeDetector().detect(context)
        self.assertFalse(any(e.event_type == MonitoringEventType.LISTING_REMOVED for e in events))

    def test_returned_listing_event(self) -> None:
        with self.db.transaction() as conn:
            self._insert_apartment(conn, "apt1", status="available")
            comparison = self._empty_comparison(new_apartment_ids=["apt1"])  # absent from the immediately-previous search
            context = self._context(
                conn, search_comparison=comparison, current_observed_apartment_ids={"apt1"},
                prior_observed_apartment_sets=[set(), {"apt1"}],  # missing last run, present 2 runs ago
            )
            events = ApartmentChangeDetector().detect(context)
        types = [e.event_type for e in events]
        self.assertIn(MonitoringEventType.LISTING_RETURNED, types)
        self.assertNotIn(MonitoringEventType.NEW_MATCH, types)  # returned takes precedence over generic new-match


class RankingChangeDetectorTests(_DetectorTestCase):
    def _result(self, apartment_id: str, rank: int, score: float) -> SearchResultEntry:
        return SearchResultEntry(search_id="s", apartment_id=apartment_id, rank=rank, score=score, score_breakdown_json="{}", price_at_search=1000.0, status_at_search="available")

    def test_rank_increase_event(self) -> None:
        with self.db.transaction() as conn:
            context = self._context(
                conn, previous_search_results=[self._result("apt1", 5, 50.0)],
                current_search_results=[self._result("apt1", 1, 90.0)],
            )
            events = RankingChangeDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.RANK_INCREASED for e in events))

    def test_rank_decrease_event(self) -> None:
        with self.db.transaction() as conn:
            context = self._context(
                conn, previous_search_results=[self._result("apt1", 1, 90.0)],
                current_search_results=[self._result("apt1", 5, 50.0)],
            )
            events = RankingChangeDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.RANK_DECREASED for e in events))

    def test_better_match_found_above_threshold(self) -> None:
        policy = MonitoringPolicy(better_match_score_threshold=5.0)
        with self.db.transaction() as conn:
            context = self._context(
                conn, policy=policy, previous_search_results=[self._result("apt1", 1, 50.0), self._result("apt2", 2, 40.0)],
                current_search_results=[self._result("apt2", 1, 70.0), self._result("apt1", 2, 50.0)],
            )
            events = RankingChangeDetector().detect(context)
        better = [e for e in events if e.event_type == MonitoringEventType.BETTER_MATCH_FOUND]
        self.assertEqual(len(better), 1)
        self.assertEqual(better[0].apartment_id, "apt2")

    def test_better_match_not_fired_below_threshold(self) -> None:
        policy = MonitoringPolicy(better_match_score_threshold=50.0)
        with self.db.transaction() as conn:
            context = self._context(
                conn, policy=policy, previous_search_results=[self._result("apt1", 1, 50.0), self._result("apt2", 2, 40.0)],
                current_search_results=[self._result("apt2", 1, 55.0), self._result("apt1", 2, 50.0)],
            )
            events = RankingChangeDetector().detect(context)
        self.assertFalse(any(e.event_type == MonitoringEventType.BETTER_MATCH_FOUND for e in events))


class FilterMatchDetectorTests(_DetectorTestCase):
    def _result(self, apartment_id: str) -> SearchResultEntry:
        return SearchResultEntry(search_id="s", apartment_id=apartment_id, rank=1, score=50.0, score_breakdown_json="{}", price_at_search=1000.0, status_at_search="available")

    def test_gained_filter_match(self) -> None:
        with self.db.transaction() as conn:
            comparison = self._empty_comparison()
            context = self._context(
                conn, search_comparison=comparison, previous_search_results=[self._result("apt1")],
                current_search_results=[self._result("apt1"), self._result("apt2")],
            )
            events = FilterMatchDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.FILTER_MATCH_GAINED and e.apartment_id == "apt2" for e in events))

    def test_lost_filter_match(self) -> None:
        with self.db.transaction() as conn:
            comparison = self._empty_comparison()
            context = self._context(
                conn, search_comparison=comparison, previous_search_results=[self._result("apt1"), self._result("apt2")],
                current_search_results=[self._result("apt1")],
            )
            events = FilterMatchDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.FILTER_MATCH_LOST and e.apartment_id == "apt2" for e in events))


class PlatformHealthDetectorTests(_DetectorTestCase):
    def test_connector_failure_event(self) -> None:
        with self.db.transaction() as conn:
            run = MonitoringRun(saved_search_id="s1", saved_search_version=1, started_at=_NOW, platforms_failed=["p1"])
            context = self._context(conn, run=run, previous_run=None)
            events = PlatformHealthDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.CONNECTOR_FAILURE and e.platform_id == "p1" for e in events))

    def test_connector_recovered_event(self) -> None:
        previous_run = MonitoringRun(saved_search_id="s1", saved_search_version=1, started_at=_NOW, platforms_failed=["p1"])
        with self.db.transaction() as conn:
            run = MonitoringRun(saved_search_id="s1", saved_search_version=1, started_at=_NOW, platforms_failed=[])
            context = self._context(conn, run=run, previous_run=previous_run)
            events = PlatformHealthDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.CONNECTOR_RECOVERED and e.platform_id == "p1" for e in events))


class DiscoveryDetectorTests(_DetectorTestCase):
    def test_no_op_without_discovery_comparison(self) -> None:
        with self.db.transaction() as conn:
            context = self._context(conn, discovery_comparison=None)
            events = DiscoveryDetector().detect(context)
        self.assertEqual(events, [])

    def test_new_platform_event(self) -> None:
        class FakeComparison:
            new_candidate_ids = ["candidate-1"]
            changed_connector_availability_candidate_ids = []

        with self.db.transaction() as conn:
            context = self._context(conn, discovery_comparison=FakeComparison())
            events = DiscoveryDetector().detect(context)
        self.assertTrue(any(e.event_type == MonitoringEventType.DISCOVERY_FOUND_NEW_PLATFORM for e in events))


if __name__ == "__main__":
    unittest.main()
