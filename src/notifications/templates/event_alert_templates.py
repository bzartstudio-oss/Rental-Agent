"""The mission's own 6 immediate-alert templates — one `MonitoringEvent` in,
one `RenderedTemplate` out. All 6 share one base (`_EventAlertTemplate`) since
they differ only in subject framing and which event types they match; the
actual apartment/report enrichment logic is identical across all of them.
"""

from __future__ import annotations

from src.monitoring.models import MonitoringEventType
from src.notifications.base_template import NotificationTemplate, RenderedTemplate, TemplateContext
from src.notifications.template_registry import register_notification_template
from src.notifications.templates import helpers


class _EventAlertTemplate(NotificationTemplate):
    version = 1
    subject_prefix: str = "Rental Agent Alert"

    def render(self, context: TemplateContext) -> RenderedTemplate:
        event = context.events[0]
        version = context.preference_version
        apartment = helpers.apartment_for_event(context.conn, event.apartment_id)

        subject = f"{self.subject_prefix}: {apartment.title if apartment else event.event_type}"
        lines = [event.explanation]
        if apartment is not None:
            lines.append(f"{apartment.title} — {apartment.current_price} ({apartment.current_status})")
        if event.old_value or event.new_value:
            lines.append(f"Changed: {event.old_value} -> {event.new_value}")

        original_urls = [apartment.url] if (apartment is not None and version.include_original_urls) else []
        report_links = helpers.report_links_for_run(context.conn, event.monitoring_run_id, include=version.include_report_links)

        if version.include_images and apartment is not None:
            images = helpers.apartment_image_paths(context.conn, event.apartment_id, include=True)
            if images:
                lines.append("Images: " + ", ".join(images))

        return RenderedTemplate(
            subject=subject, body_text="\n".join(lines), original_listing_urls=original_urls, report_links=report_links,
        )


class ImmediateApartmentAlertTemplate(_EventAlertTemplate):
    template_name = "immediate_apartment_alert"
    event_types = (MonitoringEventType.NEW_MATCH, MonitoringEventType.NEW_LISTING)
    subject_prefix = "New Match"


class PriceChangeAlertTemplate(_EventAlertTemplate):
    template_name = "price_change_alert"
    event_types = (MonitoringEventType.PRICE_DECREASED, MonitoringEventType.PRICE_INCREASED)
    subject_prefix = "Price Change"


class AvailabilityAlertTemplate(_EventAlertTemplate):
    template_name = "availability_alert"
    event_types = (
        MonitoringEventType.BECAME_AVAILABLE, MonitoringEventType.NO_LONGER_AVAILABLE,
        MonitoringEventType.AVAILABILITY_CHANGED, MonitoringEventType.AVAILABILITY_CONFIRMED,
    )
    subject_prefix = "Availability Change"


class BetterMatchAlertTemplate(_EventAlertTemplate):
    template_name = "better_match_alert"
    event_types = (MonitoringEventType.BETTER_MATCH_FOUND,)
    subject_prefix = "Better Match Found"


class ListingRemovalAlertTemplate(_EventAlertTemplate):
    template_name = "listing_removal_alert"
    event_types = (MonitoringEventType.LISTING_REMOVED, MonitoringEventType.LISTING_RETURNED)
    subject_prefix = "Listing Update"


class MonitoringFailureAlertTemplate(_EventAlertTemplate):
    template_name = "monitoring_failure_alert"
    event_types = (
        MonitoringEventType.MONITORING_RUN_FAILED, MonitoringEventType.MONITORING_RUN_PARTIAL,
        MonitoringEventType.CONNECTOR_FAILURE, MonitoringEventType.CONNECTOR_RECOVERED,
    )
    subject_prefix = "Monitoring Alert"


register_notification_template(ImmediateApartmentAlertTemplate())
register_notification_template(PriceChangeAlertTemplate())
register_notification_template(AvailabilityAlertTemplate())
register_notification_template(BetterMatchAlertTemplate())
register_notification_template(ListingRemovalAlertTemplate())
register_notification_template(MonitoringFailureAlertTemplate())
