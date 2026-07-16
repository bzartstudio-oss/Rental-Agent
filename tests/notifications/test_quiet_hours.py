"""`quiet_hours.is_in_quiet_hours()`/`next_permitted_time()` — timezone-aware,
handling both same-day and midnight-wrapping windows.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.notifications import quiet_hours
from src.notifications.models import NotificationPreferenceVersion

_MADRID = ZoneInfo("Europe/Madrid")


def _version(**overrides) -> NotificationPreferenceVersion:
    fields = dict(
        preference_id="pref-1", version=1, enabled_channels=["console"], event_types=[], immediate_event_types=[],
        digest_event_types=[], timezone="Europe/Madrid", include_images=True, include_original_urls=True,
        include_ranking_explanation=True, include_geo_summary=True, include_preference_explanation=True,
        include_report_links=True, language="en", format="text", metadata={},
        created_at=datetime(2026, 7, 16, tzinfo=timezone.utc), quiet_hours_start="22:00", quiet_hours_end="07:00",
    )
    fields.update(overrides)
    return NotificationPreferenceVersion(**fields)


class QuietHoursTests(unittest.TestCase):
    def test_no_quiet_hours_configured_is_never_in_quiet_hours(self) -> None:
        version = _version(quiet_hours_start=None, quiet_hours_end=None)
        now = datetime(2026, 7, 16, 23, 0, tzinfo=timezone.utc)
        self.assertFalse(quiet_hours.is_in_quiet_hours(version, now))

    def test_midnight_wrapping_window_is_in_quiet_hours_late_at_night(self) -> None:
        version = _version()  # 22:00-07:00 Europe/Madrid
        now_local = datetime(2026, 7, 16, 23, 30, tzinfo=_MADRID)
        self.assertTrue(quiet_hours.is_in_quiet_hours(version, now_local))

    def test_midnight_wrapping_window_is_in_quiet_hours_early_morning(self) -> None:
        version = _version()
        now_local = datetime(2026, 7, 17, 5, 0, tzinfo=_MADRID)
        self.assertTrue(quiet_hours.is_in_quiet_hours(version, now_local))

    def test_midnight_wrapping_window_is_not_in_quiet_hours_midday(self) -> None:
        version = _version()
        now_local = datetime(2026, 7, 16, 14, 0, tzinfo=_MADRID)
        self.assertFalse(quiet_hours.is_in_quiet_hours(version, now_local))

    def test_same_day_window_is_in_quiet_hours_within_range(self) -> None:
        version = _version(quiet_hours_start="09:00", quiet_hours_end="17:00")
        now_local = datetime(2026, 7, 16, 12, 0, tzinfo=_MADRID)
        self.assertTrue(quiet_hours.is_in_quiet_hours(version, now_local))

    def test_same_day_window_is_not_in_quiet_hours_outside_range(self) -> None:
        version = _version(quiet_hours_start="09:00", quiet_hours_end="17:00")
        now_local = datetime(2026, 7, 16, 20, 0, tzinfo=_MADRID)
        self.assertFalse(quiet_hours.is_in_quiet_hours(version, now_local))

    def test_a_naive_datetime_is_interpreted_in_the_preference_timezone(self) -> None:
        version = _version()
        naive_now = datetime(2026, 7, 16, 23, 30)  # no tzinfo
        self.assertTrue(quiet_hours.is_in_quiet_hours(version, naive_now))

    def test_next_permitted_time_returns_now_when_not_in_quiet_hours(self) -> None:
        version = _version(quiet_hours_start="09:00", quiet_hours_end="17:00")
        now_local = datetime(2026, 7, 16, 20, 0, tzinfo=_MADRID)  # outside 09:00-17:00
        self.assertEqual(quiet_hours.next_permitted_time(version, now_local), now_local)

    def test_next_permitted_time_during_quiet_hours_is_the_configured_end_time_same_day(self) -> None:
        version = _version()  # 22:00-07:00
        now_local = datetime(2026, 7, 16, 23, 30, tzinfo=_MADRID)
        next_time = quiet_hours.next_permitted_time(version, now_local)
        self.assertEqual((next_time.hour, next_time.minute), (7, 0))
        self.assertEqual(next_time.date(), datetime(2026, 7, 17).date())

    def test_next_permitted_time_after_midnight_still_resolves_to_the_same_upcoming_end(self) -> None:
        version = _version()  # 22:00-07:00
        now_local = datetime(2026, 7, 17, 5, 0, tzinfo=_MADRID)
        next_time = quiet_hours.next_permitted_time(version, now_local)
        self.assertEqual((next_time.hour, next_time.minute), (7, 0))
        self.assertEqual(next_time.date(), datetime(2026, 7, 17).date())


if __name__ == "__main__":
    unittest.main()
