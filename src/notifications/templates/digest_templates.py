"""The mission's own digest templates — `daily_digest`/`weekly_digest` share
one implementation (`_DigestTemplate`) since the actual grouping/ordering
logic is identical regardless of period length; only the subject label
differs. Hourly/manual digests reuse the same shared base directly (see
`engine.py` — they're the same rendering, just a different `context.frequency`
label), so no third/fourth template class is needed for them.
"""

from __future__ import annotations

from collections import defaultdict

from src.monitoring.models import MonitoringEventType
from src.notifications.base_template import NotificationTemplate, RenderedTemplate, TemplateContext
from src.notifications.template_registry import register_notification_template
from src.notifications.templates import helpers

_PRICE_TYPES = (MonitoringEventType.PRICE_DECREASED, MonitoringEventType.PRICE_INCREASED)
_AVAILABILITY_TYPES = (MonitoringEventType.BECAME_AVAILABLE, MonitoringEventType.NO_LONGER_AVAILABLE, MonitoringEventType.AVAILABILITY_CHANGED)
_RANKING_TYPES = (MonitoringEventType.RANK_INCREASED, MonitoringEventType.RANK_DECREASED, MonitoringEventType.BETTER_MATCH_FOUND)
_NEW_MATCH_TYPES = (MonitoringEventType.NEW_MATCH, MonitoringEventType.NEW_LISTING)
_FAILURE_TYPES = (MonitoringEventType.MONITORING_RUN_FAILED, MonitoringEventType.MONITORING_RUN_PARTIAL, MonitoringEventType.CONNECTOR_FAILURE)


class _DigestTemplate(NotificationTemplate):
    version = 1
    event_types = ()  # digests aren't matched by event type — they're triggered by preference.digest_frequency

    def render(self, context: TemplateContext) -> RenderedTemplate:
        events = context.events
        by_saved_search: dict[str, list] = defaultdict(list)
        for event in events:
            by_saved_search[event.saved_search_id].append(event)

        new_matches = sorted((e for e in events if e.event_type in _NEW_MATCH_TYPES), key=lambda e: e.significance, reverse=True)
        price_changes = [e for e in events if e.event_type in _PRICE_TYPES]
        availability_changes = [e for e in events if e.event_type in _AVAILABILITY_TYPES]
        ranking_changes = [e for e in events if e.event_type in _RANKING_TYPES]
        failures = [e for e in events if e.event_type in _FAILURE_TYPES]

        frequency_label = (context.frequency or "digest").capitalize()
        subject = f"{frequency_label} Digest" + (f" — {context.saved_search_name}" if context.saved_search_name and len(by_saved_search) == 1 else "")

        lines = [f"{frequency_label} summary: {len(events)} event(s) across {len(by_saved_search)} saved search(es)."]

        if new_matches:
            lines.append("\nTop new matches:")
            for event in new_matches[:5]:
                lines.append(f"  - {event.explanation} (significance {event.significance:.2f})")

        if price_changes:
            lines.append("\nPrice changes:")
            for event in price_changes:
                lines.append(f"  - {event.explanation}")

        if availability_changes:
            lines.append("\nAvailability changes:")
            for event in availability_changes:
                lines.append(f"  - {event.explanation}")

        if ranking_changes:
            lines.append("\nRanking changes:")
            for event in ranking_changes:
                lines.append(f"  - {event.explanation}")

        if failures:
            lines.append("\nFailed platforms / monitoring issues:")
            for event in failures:
                lines.append(f"  - {event.explanation}")

        original_urls = []
        report_links: list[str] = []
        if context.preference_version.include_original_urls:
            for event in events:
                apartment = helpers.apartment_for_event(context.conn, event.apartment_id)
                if apartment is not None and apartment.url not in original_urls:
                    original_urls.append(apartment.url)

        if context.preference_version.include_report_links:
            seen_runs: set[str] = set()
            for event in events:
                if event.monitoring_run_id and event.monitoring_run_id not in seen_runs:
                    seen_runs.add(event.monitoring_run_id)
                    report_links.extend(helpers.report_links_for_run(context.conn, event.monitoring_run_id, include=True))

        return RenderedTemplate(subject=subject, body_text="\n".join(lines), original_listing_urls=original_urls, report_links=report_links)


class DailyDigestTemplate(_DigestTemplate):
    template_name = "daily_digest"


class WeeklyDigestTemplate(_DigestTemplate):
    template_name = "weekly_digest"


register_notification_template(DailyDigestTemplate())
register_notification_template(WeeklyDigestTemplate())
