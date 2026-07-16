"""Performance regression tests for the Feedback + Preference Learning Engine —
recording many real events against all 23 real built-in rules, and building a
profile from a large accumulated history, must both stay fast. Mirrors
`tests/ranking_v2/test_performance.py`/`tests/filter_engine/test_performance.py`'s
same "the whole point of a plugin architecture is that scale doesn't degrade the
framework" reasoning.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.feedback.engine import FeedbackEngine
from src.feedback.event_types import FeedbackEventType
from src.feedback.models import FeedbackEvent
from src.storage.database import Database
from src.storage.models import Apartment, Platform

_NOW = datetime.now(timezone.utc)


class FeedbackEnginePerformanceTests(unittest.TestCase):
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

    def test_recording_500_events_against_all_23_rules_stays_fast(self) -> None:
        apt = Apartment(
            id="apt-1", platform_id="p1", platform_listing_id="l1", title="T", url="u", current_price=1000,
            current_status="available", first_seen_at=_NOW, last_seen_at=_NOW, property_type="apartment",
            sqft=500, bedrooms=1,
        )

        started = time.perf_counter()
        with self.db.transaction() as conn:
            for i in range(500):
                self.engine.record_event(
                    conn,
                    FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED,
                                  occurred_at=_NOW - timedelta(hours=i), source="cli", apartment_id="apt-1"),
                    apartment=apt,
                )
        elapsed_s = time.perf_counter() - started

        self.assertLess(elapsed_s, 10.0, "recording 500 events against 23 rules took too long")

    def test_building_a_profile_from_500_accumulated_observations_stays_fast(self) -> None:
        apt = Apartment(
            id="apt-1", platform_id="p1", platform_listing_id="l1", title="T", url="u", current_price=1000,
            current_status="available", first_seen_at=_NOW, last_seen_at=_NOW, property_type="apartment",
            sqft=500, bedrooms=1,
        )
        with self.db.transaction() as conn:
            for i in range(500):
                self.engine.record_event(
                    conn,
                    FeedbackEvent(profile_id="u1", event_type=FeedbackEventType.SAVED,
                                  occurred_at=_NOW - timedelta(hours=i), source="cli", apartment_id="apt-1"),
                    apartment=apt,
                )

            started = time.perf_counter()
            profile = self.engine.build_preference_profile(conn, "u1", now=_NOW)
            elapsed_s = time.perf_counter() - started

        self.assertEqual(len(profile.preferences), 23)
        self.assertLess(elapsed_s, 5.0, "building a profile from 500 observations took too long")


if __name__ == "__main__":
    unittest.main()
