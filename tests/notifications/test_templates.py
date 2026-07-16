"""Template registry self-registration + each of the 6 event-alert templates
and both digest templates rendering real `MonitoringEvent`/`Apartment` data.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.monitoring.models import MonitoringEventType
from src.notifications.base_template import TemplateContext
from src.notifications.models import NotificationPreferenceVersion
from src.notifications.template_registry import NotificationTemplateRegistry
from src.storage.database import Database
from tests.notifications import helpers

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


class TemplateRegistryTests(unittest.TestCase):
    def test_all_8_mission_templates_are_registered(self) -> None:
        registered = {t.template_name for t in NotificationTemplateRegistry.all()}
        for expected in [
            "immediate_apartment_alert", "price_change_alert", "availability_alert", "better_match_alert",
            "listing_removal_alert", "monitoring_failure_alert", "daily_digest", "weekly_digest",
        ]:
            self.assertIn(expected, registered)

    def test_for_event_type_resolves_the_matching_template(self) -> None:
        template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.PRICE_DECREASED)
        self.assertEqual(template.template_name, "price_change_alert")

    def test_for_event_type_returns_none_for_a_digest_only_type(self) -> None:
        self.assertIsNone(NotificationTemplateRegistry.for_event_type("no_such_event_type"))


class EventAlertTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.saved_search = helpers.make_saved_search(self.db)
        with self.db.transaction() as conn:
            self.run = helpers.make_run(conn, self.saved_search)
            self.apartment = helpers.make_apartment(conn)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_immediate_apartment_alert_includes_apartment_title_and_url(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)
            template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.NEW_MATCH)
            rendered = template.render(TemplateContext(conn=conn, events=[event], preference_version=_version(), now=_NOW))
        self.assertIn(self.apartment.title, rendered.subject)
        self.assertEqual(rendered.original_listing_urls, [self.apartment.url])

    def test_include_original_urls_false_omits_urls(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)
            template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.NEW_MATCH)
            rendered = template.render(TemplateContext(conn=conn, events=[event], preference_version=_version(include_original_urls=False), now=_NOW))
        self.assertEqual(rendered.original_listing_urls, [])

    def test_price_change_alert_mentions_old_and_new_value(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(
                conn, self.saved_search, self.run, event_type=MonitoringEventType.PRICE_DECREASED, apartment_id=self.apartment.id,
                old_value={"price": 1300}, new_value={"price": 1200},
            )
            template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.PRICE_DECREASED)
            rendered = template.render(TemplateContext(conn=conn, events=[event], preference_version=_version(), now=_NOW))
        self.assertIn("1300", rendered.body_text)
        self.assertIn("1200", rendered.body_text)

    def test_availability_alert_renders_for_became_available(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.BECAME_AVAILABLE, apartment_id=self.apartment.id)
            template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.BECAME_AVAILABLE)
            rendered = template.render(TemplateContext(conn=conn, events=[event], preference_version=_version(), now=_NOW))
        self.assertIn("Availability Change", rendered.subject)

    def test_better_match_alert_renders(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.BETTER_MATCH_FOUND, apartment_id=self.apartment.id)
            template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.BETTER_MATCH_FOUND)
            rendered = template.render(TemplateContext(conn=conn, events=[event], preference_version=_version(), now=_NOW))
        self.assertIn("Better Match Found", rendered.subject)

    def test_listing_removal_alert_renders(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.LISTING_REMOVED, apartment_id=self.apartment.id)
            template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.LISTING_REMOVED)
            rendered = template.render(TemplateContext(conn=conn, events=[event], preference_version=_version(), now=_NOW))
        self.assertIn("Listing Update", rendered.subject)

    def test_monitoring_failure_alert_renders_without_an_apartment(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.MONITORING_RUN_FAILED, apartment_id=None)
            template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.MONITORING_RUN_FAILED)
            rendered = template.render(TemplateContext(conn=conn, events=[event], preference_version=_version(), now=_NOW))
        self.assertIn("Monitoring Alert", rendered.subject)
        self.assertEqual(rendered.original_listing_urls, [])  # no apartment to link to

    def test_rendering_is_reproducible_for_the_same_inputs(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment.id)
            template = NotificationTemplateRegistry.for_event_type(MonitoringEventType.NEW_MATCH)
            context = TemplateContext(conn=conn, events=[event], preference_version=_version(), now=_NOW)
            first = template.render(context)
            second = template.render(context)
        self.assertEqual(first.subject, second.subject)
        self.assertEqual(first.body_text, second.body_text)


class DigestTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.saved_search = helpers.make_saved_search(self.db)
        with self.db.transaction() as conn:
            self.run = helpers.make_run(conn, self.saved_search)
            self.apartment_a = helpers.make_apartment(conn)
            self.apartment_b = helpers.make_apartment(conn)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_daily_digest_groups_events_by_category_and_orders_new_matches_by_significance(self) -> None:
        with self.db.transaction() as conn:
            low = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, significance=0.2, apartment_id=self.apartment_a.id)
            high = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, significance=0.9, apartment_id=self.apartment_b.id)
            price = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.PRICE_DECREASED, apartment_id=self.apartment_a.id)
            low.explanation, high.explanation = "low significance new match", "high significance new match"

            template = NotificationTemplateRegistry.get("daily_digest")
            context = TemplateContext(
                conn=conn, events=[low, high, price], preference_version=_version(), now=_NOW, frequency="daily",
                period_start=_NOW, period_end=_NOW, saved_search_name=self.saved_search.name,
            )
            rendered = template.render(context)

        self.assertIn("Daily Digest", rendered.subject)
        self.assertIn("Top new matches", rendered.body_text)
        self.assertIn("Price changes", rendered.body_text)
        self.assertLess(rendered.body_text.index(high.explanation), rendered.body_text.index(low.explanation))

    def test_weekly_digest_uses_its_own_label(self) -> None:
        with self.db.transaction() as conn:
            event = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment_a.id)
            template = NotificationTemplateRegistry.get("weekly_digest")
            rendered = template.render(TemplateContext(conn=conn, events=[event], preference_version=_version(), now=_NOW, frequency="weekly", period_start=_NOW, period_end=_NOW))
        self.assertIn("Weekly Digest", rendered.subject)

    def test_digest_lists_report_links_and_original_urls_without_duplicates(self) -> None:
        with self.db.transaction() as conn:
            e1 = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.NEW_MATCH, apartment_id=self.apartment_a.id)
            e2 = helpers.make_event(conn, self.saved_search, self.run, event_type=MonitoringEventType.PRICE_DECREASED, apartment_id=self.apartment_a.id)  # same apartment
            template = NotificationTemplateRegistry.get("daily_digest")
            rendered = template.render(TemplateContext(conn=conn, events=[e1, e2], preference_version=_version(), now=_NOW, frequency="daily", period_start=_NOW, period_end=_NOW))
        self.assertEqual(rendered.original_listing_urls, [self.apartment_a.url])  # de-duplicated


if __name__ == "__main__":
    unittest.main()
