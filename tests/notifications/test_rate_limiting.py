"""`rate_limiting.is_rate_limited()`/`record_send()` — per-profile/per-channel
hourly/daily caps. "Rate-limit suppression must be stored and explainable"
(the mission's own words) is exercised at the engine level
(`test_engine.py`); this module covers the counting logic in isolation.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.notifications import rate_limiting
from src.notifications.models import NotificationPreferenceVersion
from src.storage.database import Database

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


def _version(**overrides) -> NotificationPreferenceVersion:
    fields = dict(
        preference_id="pref-1", version=1, enabled_channels=["console"], event_types=[], immediate_event_types=[],
        digest_event_types=[], timezone="UTC", include_images=True, include_original_urls=True,
        include_ranking_explanation=True, include_geo_summary=True, include_preference_explanation=True,
        include_report_links=True, language="en", format="text", metadata={}, created_at=_NOW,
    )
    fields.update(overrides)
    return NotificationPreferenceVersion(**fields)


class RateLimitingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_no_limits_configured_never_rate_limits(self) -> None:
        with self.db.transaction() as conn:
            for _ in range(50):
                rate_limiting.record_send(conn, "profile-1", "console", _NOW)
            self.assertFalse(rate_limiting.is_rate_limited(conn, "profile-1", "console", _version(), _NOW))

    def test_hourly_limit_is_enforced_once_reached(self) -> None:
        version = _version(max_per_hour=3)
        with self.db.transaction() as conn:
            for _ in range(3):
                rate_limiting.record_send(conn, "profile-1", "console", _NOW)
            self.assertTrue(rate_limiting.is_rate_limited(conn, "profile-1", "console", version, _NOW))

    def test_below_hourly_limit_is_not_rate_limited(self) -> None:
        version = _version(max_per_hour=3)
        with self.db.transaction() as conn:
            rate_limiting.record_send(conn, "profile-1", "console", _NOW)
            self.assertFalse(rate_limiting.is_rate_limited(conn, "profile-1", "console", version, _NOW))

    def test_daily_limit_is_enforced_once_reached(self) -> None:
        version = _version(max_per_day=2)
        with self.db.transaction() as conn:
            rate_limiting.record_send(conn, "profile-1", "console", _NOW - timedelta(hours=5))
            rate_limiting.record_send(conn, "profile-1", "console", _NOW - timedelta(hours=1))
            self.assertTrue(rate_limiting.is_rate_limited(conn, "profile-1", "console", version, _NOW))

    def test_observations_older_than_the_window_do_not_count(self) -> None:
        version = _version(max_per_hour=1)
        with self.db.transaction() as conn:
            rate_limiting.record_send(conn, "profile-1", "console", _NOW - timedelta(hours=2))
            self.assertFalse(rate_limiting.is_rate_limited(conn, "profile-1", "console", version, _NOW))

    def test_rate_limits_are_isolated_per_channel(self) -> None:
        version = _version(max_per_hour=1)
        with self.db.transaction() as conn:
            rate_limiting.record_send(conn, "profile-1", "console", _NOW)
            self.assertFalse(rate_limiting.is_rate_limited(conn, "profile-1", "file", version, _NOW))

    def test_rate_limits_are_isolated_per_profile(self) -> None:
        version = _version(max_per_hour=1)
        with self.db.transaction() as conn:
            rate_limiting.record_send(conn, "profile-1", "console", _NOW)
            self.assertFalse(rate_limiting.is_rate_limited(conn, "profile-2", "console", version, _NOW))


if __name__ == "__main__":
    unittest.main()
