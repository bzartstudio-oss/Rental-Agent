"""`eligibility.evaluate_event()` — deterministic and explainable: every
ineligible outcome must name its exact reason, never a bare `False`. Quiet
hours/rate limits are deliberately out of scope here (see `test_quiet_hours.py`/
`test_rate_limiting.py`) — this module only covers content-based eligibility.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.monitoring.models import MonitoringEventType
from src.notifications import eligibility
from src.notifications.models import NotificationPreference, NotificationPreferenceVersion
from src.storage.database import Database
from tests.notifications import helpers

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


def _preference(*, enabled=True) -> NotificationPreference:
    return NotificationPreference(
        preference_id="pref-1", profile_id="profile-1", current_version=1, enabled=enabled, created_at=_NOW, updated_at=_NOW,
    )


def _version(**overrides) -> NotificationPreferenceVersion:
    fields = dict(
        preference_id="pref-1", version=1, enabled_channels=["console"], event_types=[], immediate_event_types=["new_match"],
        digest_event_types=[], timezone="UTC", include_images=True, include_original_urls=True, include_ranking_explanation=True,
        include_geo_summary=True, include_preference_explanation=True, include_report_links=True, language="en", format="text",
        metadata={}, created_at=_NOW, minimum_severity=None, minimum_significance=0.0, digest_frequency=None,
    )
    fields.update(overrides)
    return NotificationPreferenceVersion(**fields)


class EligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.saved_search = helpers.make_saved_search(self.db)
        with self.db.transaction() as conn:
            self.run = helpers.make_run(conn, self.saved_search)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _event(self, **overrides):
        with self.db.transaction() as conn:
            return helpers.make_event(conn, self.saved_search, self.run, **overrides)

    def test_eligible_event_resolves_console_as_an_eligible_channel(self) -> None:
        event = self._event(event_type=MonitoringEventType.NEW_MATCH)
        result = eligibility.evaluate_event(event, _preference(), _version())
        self.assertTrue(result.eligible)
        self.assertEqual(result.eligible_channels, ["console"])
        self.assertTrue(result.is_immediate)

    def test_disabled_preference_is_ineligible_with_a_named_reason(self) -> None:
        event = self._event()
        result = eligibility.evaluate_event(event, _preference(enabled=False), _version())
        self.assertFalse(result.eligible)
        self.assertIn("disabled", result.ineligible_reasons["*"])

    def test_already_acknowledged_event_is_ineligible(self) -> None:
        event = self._event(acknowledged=True)
        result = eligibility.evaluate_event(event, _preference(), _version())
        self.assertFalse(result.eligible)
        self.assertIn("acknowledged", result.ineligible_reasons["*"])

    def test_event_marked_not_notification_eligible_is_ineligible(self) -> None:
        event = self._event(notification_eligible=False)
        result = eligibility.evaluate_event(event, _preference(), _version())
        self.assertFalse(result.eligible)
        self.assertIn("notification_eligible", result.ineligible_reasons["*"])

    def test_event_type_not_opted_in_is_ineligible(self) -> None:
        event = self._event(event_type=MonitoringEventType.PRICE_DECREASED)
        result = eligibility.evaluate_event(event, _preference(), _version(event_types=["new_match"]))
        self.assertFalse(result.eligible)
        self.assertIn("event_type", result.ineligible_reasons["*"])

    def test_severity_below_minimum_is_ineligible(self) -> None:
        event = self._event(severity="info")
        result = eligibility.evaluate_event(event, _preference(), _version(minimum_severity="critical"))
        self.assertFalse(result.eligible)
        self.assertIn("severity", result.ineligible_reasons["*"])

    def test_significance_below_minimum_is_ineligible(self) -> None:
        event = self._event(significance=0.1)
        result = eligibility.evaluate_event(event, _preference(), _version(minimum_significance=0.5))
        self.assertFalse(result.eligible)
        self.assertIn("significance", result.ineligible_reasons["*"])

    def test_channel_not_registered_produces_a_per_channel_reason(self) -> None:
        event = self._event()
        result = eligibility.evaluate_event(event, _preference(), _version(enabled_channels=["not_a_real_channel"]))
        self.assertFalse(result.eligible)
        self.assertIn("not registered", result.ineligible_reasons["not_a_real_channel"])

    def test_channel_registered_but_disabled_produces_a_per_channel_reason(self) -> None:
        event = self._event()
        result = eligibility.evaluate_event(event, _preference(), _version(enabled_channels=["email"]))  # disabled by default
        self.assertFalse(result.eligible)
        self.assertIn("not currently configured", result.ineligible_reasons["email"])

    def test_event_type_not_in_immediate_but_digest_frequency_set_is_digest_only(self) -> None:
        event = self._event(event_type=MonitoringEventType.PRICE_DECREASED)
        result = eligibility.evaluate_event(event, _preference(), _version(immediate_event_types=["new_match"], digest_frequency="daily"))
        self.assertTrue(result.eligible)
        self.assertFalse(result.is_immediate)
        self.assertTrue(result.is_digest_only)

    def test_explain_eligibility_describes_eligible_and_ineligible_outcomes(self) -> None:
        eligible_event = self._event(event_type=MonitoringEventType.NEW_MATCH)
        eligible_result = eligibility.evaluate_event(eligible_event, _preference(), _version())
        self.assertIn("Eligible", eligibility.explain_eligibility(eligible_result))

        ineligible_result = eligibility.evaluate_event(self._event(acknowledged=True), _preference(), _version())
        self.assertIn("Ineligible", eligibility.explain_eligibility(ineligible_result))

    def test_eligible_channels_and_ineligible_reasons_accessors(self) -> None:
        event = self._event(event_type=MonitoringEventType.NEW_MATCH)
        result = eligibility.evaluate_event(event, _preference(), _version())
        self.assertEqual(eligibility.eligible_channels(result), ["console"])
        self.assertEqual(eligibility.ineligible_reasons(result), {})


if __name__ == "__main__":
    unittest.main()
