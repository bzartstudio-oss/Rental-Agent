"""Unit + Integration + Reproducibility tests for FeedbackEngine —
src/feedback/engine.py. Covers exactly the mission's own "Test that" list:
one event never creates an extreme preference, repeated consistent events
strengthen confidence, conflicting events reduce confidence, explicit
preferences override inferred ones, missing listing fields never become
negative signals, old feedback remains historically reproducible, resetting
inferred preferences never deletes raw events, undo is real.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.feedback.engine import FeedbackEngine
from src.feedback.event_types import FeedbackEventType
from src.feedback.exceptions import FeedbackConfigurationError, FeedbackValidationError
from src.feedback.models import FeedbackEvent, FeedbackMode
from src.storage.database import Database
from src.storage.models import Apartment, Platform

_NOW = datetime.now(timezone.utc)


def _apartment(apartment_id="apt-1", **kwargs) -> Apartment:
    defaults = dict(
        id=apartment_id, platform_id="p1", platform_listing_id=apartment_id, title="Test", url="u",
        current_price=1000, current_status="available", first_seen_at=_NOW, last_seen_at=_NOW,
        property_type="apartment", sqft=500, bedrooms=1,
    )
    defaults.update(kwargs)
    return Apartment(**defaults)


class FeedbackEngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn, Platform(id="p1", name="P1", country="N/A", homepage="n/a",
                                connector_available=False, connector_name=None, created_at=_NOW),
            )
        self.engine = FeedbackEngine()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()


class RecordEventTests(FeedbackEngineTestCase):
    def test_record_event_persists_it(self) -> None:
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.VIEWED, occurred_at=_NOW, source="cli")
        with self.db.transaction() as conn:
            self.engine.record_event(conn, event)
            exported = self.engine.export_feedback_history(conn, "u1")
        self.assertEqual(len(exported), 1)

    def test_empty_profile_id_raises_validation_error(self) -> None:
        event = FeedbackEvent(profile_id="", event_type=FeedbackEventType.VIEWED, occurred_at=_NOW, source="cli")
        with self.db.transaction() as conn:
            with self.assertRaises(FeedbackValidationError):
                self.engine.record_event(conn, event)

    def test_recording_generates_observations_for_relevant_rules(self) -> None:
        apt = _apartment()
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli", apartment_id="apt-1")
        with self.db.transaction() as conn:
            self.engine.record_event(conn, event, apartment=apt)
            evidence = self.engine.explain_preference(conn, "u1", "property_type")
        self.assertEqual(evidence.supporting_count, 1)


class SingleActionTests(FeedbackEngineTestCase):
    def test_one_event_does_not_create_an_extreme_preference(self) -> None:
        apt = _apartment()
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli", apartment_id="apt-1")
        with self.db.transaction() as conn:
            self.engine.record_event(conn, event, apartment=apt)
            profile = self.engine.build_preference_profile(conn, "u1", now=_NOW)
        self.assertLess(profile.preferences["property_type"].confidence.overall, 0.5)


class RepeatedEvidenceTests(FeedbackEngineTestCase):
    def test_repeated_consistent_events_strengthen_confidence(self) -> None:
        apt = _apartment()
        with self.db.transaction() as conn:
            for i in range(2):
                self.engine.record_event(
                    conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED,
                                         occurred_at=_NOW - timedelta(hours=i), source="cli", apartment_id="apt-1"),
                    apartment=apt,
                )
            profile_after_two = self.engine.build_preference_profile(conn, "u1", now=_NOW)

            for i in range(2, 8):
                self.engine.record_event(
                    conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED,
                                         occurred_at=_NOW - timedelta(hours=i), source="cli", apartment_id="apt-1"),
                    apartment=apt,
                )
            profile_after_eight = self.engine.build_preference_profile(conn, "u1", now=_NOW)

        self.assertGreater(
            profile_after_eight.preferences["property_type"].confidence.overall,
            profile_after_two.preferences["property_type"].confidence.overall,
        )

    def test_conflicting_events_reduce_confidence(self) -> None:
        available_apt = _apartment("apt-avail", current_status="available")
        unavailable_apt = _apartment("apt-unavail", current_status="delisted")
        with self.db.transaction() as conn:
            for _ in range(3):
                self.engine.record_event(
                    conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                         source="cli", apartment_id="apt-avail"),
                    apartment=available_apt,
                )
                self.engine.record_event(
                    conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                         source="cli", apartment_id="apt-unavail"),
                    apartment=unavailable_apt,
                )
            conflicted_profile = self.engine.build_preference_profile(conn, "u1", now=_NOW)

        with self.db.transaction() as conn2:
            for _ in range(6):
                self.engine.record_event(
                    conn2, FeedbackEvent(profile_id="u2", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                          source="cli", apartment_id="apt-avail"),
                    apartment=available_apt,
                )
            consistent_profile = self.engine.build_preference_profile(conn2, "u2", now=_NOW)

        self.assertLess(
            conflicted_profile.preferences["availability_importance"].confidence.overall,
            consistent_profile.preferences["availability_importance"].confidence.overall,
        )


class MissingEvidenceTests(FeedbackEngineTestCase):
    def test_missing_listing_fields_are_never_a_negative_signal(self) -> None:
        """An apartment with no `sqft` must never make `minimum_area` look like it
        opposes anything — it must simply have no evidence.
        """
        apt = _apartment(sqft=None)
        event = FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli", apartment_id="apt-1")
        with self.db.transaction() as conn:
            self.engine.record_event(conn, event, apartment=apt)
            profile = self.engine.build_preference_profile(conn, "u1", now=_NOW)
        self.assertIsNone(profile.preferences["minimum_area"].current_value)
        self.assertEqual(profile.preferences["minimum_area"].confidence.opposing_evidence_count, 0)


class ExplicitPrecedenceTests(FeedbackEngineTestCase):
    def test_explicit_settings_override_inferred_evidence(self) -> None:
        apt = _apartment(property_type="studio")
        with self.db.transaction() as conn:
            for _ in range(5):
                self.engine.record_event(
                    conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                         source="cli", apartment_id="apt-1"),
                    apartment=apt,
                )
            profile = self.engine.build_preference_profile(
                conn, "u1", explicit_settings={"property_type": {"preferred": "house"}}, now=_NOW
            )
        self.assertEqual(profile.preferences["property_type"].current_value, {"preferred": "house"})
        self.assertTrue(profile.preferences["property_type"].is_explicit)
        self.assertEqual(profile.preferences["property_type"].confidence.overall, 1.0)


class UndoResetTests(FeedbackEngineTestCase):
    def test_undo_restores_the_previous_value(self) -> None:
        apt = _apartment()
        with self.db.transaction() as conn:
            self.engine.record_event(
                conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                     source="cli", apartment_id="apt-1"),
                apartment=apt,
            )
            self.engine.build_preference_profile(conn, "u1", now=_NOW)
            history = self.engine.get_preference_history(conn, "u1", "property_type")
            self.assertEqual(len(history), 1)

            undo = self.engine.undo_preference_adjustment(conn, "u1", "property_type", history[-1].id, now=_NOW)
        self.assertIsNone(undo.new_value)  # nothing before the first adjustment

    def test_undo_raises_for_a_mismatched_adjustment(self) -> None:
        with self.db.transaction() as conn:
            with self.assertRaises(FeedbackConfigurationError):
                self.engine.undo_preference_adjustment(conn, "u1", "property_type", 999)

    def test_reset_does_not_delete_raw_feedback_events(self) -> None:
        apt = _apartment()
        with self.db.transaction() as conn:
            self.engine.record_event(
                conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                     source="cli", apartment_id="apt-1"),
                apartment=apt,
            )
            self.engine.build_preference_profile(conn, "u1", now=_NOW)
            self.engine.reset_inferred_preferences(conn, "u1", now=_NOW + timedelta(seconds=1))
            exported = self.engine.export_feedback_history(conn, "u1")
        self.assertEqual(len(exported), 1)  # the raw event is still there

    def test_reset_never_touches_explicit_preferences(self) -> None:
        apt = _apartment()
        with self.db.transaction() as conn:
            self.engine.record_event(
                conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                     source="cli", apartment_id="apt-1"),
                apartment=apt,
            )
            self.engine.build_preference_profile(
                conn, "u1", explicit_settings={"property_type": {"preferred": "house"}}, now=_NOW
            )
            resets = self.engine.reset_inferred_preferences(conn, "u1", now=_NOW + timedelta(seconds=1))
        self.assertFalse(any(r.preference_key == "property_type" for r in resets))

    def test_reset_then_rebuild_shows_no_evidence_until_new_events(self) -> None:
        apt = _apartment()
        with self.db.transaction() as conn:
            self.engine.record_event(
                conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                     source="cli", apartment_id="apt-1"),
                apartment=apt,
            )
            self.engine.build_preference_profile(conn, "u1", now=_NOW)
            self.engine.reset_inferred_preferences(conn, "u1", now=_NOW + timedelta(seconds=1))
            rebuilt = self.engine.build_preference_profile(conn, "u1", now=_NOW + timedelta(seconds=2))
        self.assertIsNone(rebuilt.preferences["property_type"].current_value)


class ReproducibilityTests(FeedbackEngineTestCase):
    def test_old_feedback_remains_historically_reproducible(self) -> None:
        """Building the profile twice from the same, unchanged history at the same
        reference time gives byte-identical results.
        """
        apt = _apartment()
        with self.db.transaction() as conn:
            self.engine.record_event(
                conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                     source="cli", apartment_id="apt-1"),
                apartment=apt,
            )
            profile1 = self.engine.build_preference_profile(conn, "u1", now=_NOW + timedelta(days=10))
            profile2 = self.engine.build_preference_profile(conn, "u1", now=_NOW + timedelta(days=10))
        self.assertEqual(
            profile1.preferences["property_type"].current_value, profile2.preferences["property_type"].current_value,
        )
        self.assertEqual(
            profile1.preferences["property_type"].confidence.overall, profile2.preferences["property_type"].confidence.overall,
        )


class CompareProfilesTests(FeedbackEngineTestCase):
    def test_compare_profiles_reports_differences(self) -> None:
        apartment_type = _apartment(property_type="apartment")
        house_type = _apartment("apt-2", property_type="house")
        with self.db.transaction() as conn:
            self.engine.record_event(
                conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                     source="cli", apartment_id="apt-1"),
                apartment=apartment_type,
            )
            self.engine.record_event(
                conn, FeedbackEvent(profile_id="u2", event_type=FeedbackEventType.SAVED, occurred_at=_NOW,
                                     source="cli", apartment_id="apt-2"),
                apartment=house_type,
            )
            comparison = self.engine.compare_preference_profiles(conn, "u1", "u2", now=_NOW)
        self.assertIn("property_type", comparison["differences"])


class StatisticsTests(FeedbackEngineTestCase):
    def test_compute_statistics_counts_events_by_type(self) -> None:
        with self.db.transaction() as conn:
            self.engine.record_event(conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.VIEWED, occurred_at=_NOW, source="cli"))
            self.engine.record_event(conn, FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED, occurred_at=_NOW, source="cli"))
            stats = self.engine.compute_statistics(conn, "u1")
        self.assertEqual(stats.total_events, 2)
        self.assertEqual(stats.events_by_type["viewed"], 1)


if __name__ == "__main__":
    unittest.main()
