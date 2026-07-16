"""`ApartmentChangeDetector` — new matches, price/availability changes, listing
detail updates, and removal-threshold tracking. Reuses `SearchComparison`
(Search Memory) and `history_service.change_timeline()` (Apartment History)
directly rather than re-diffing apartments itself — see
docs/30_Continuous_Monitoring.md "Change Detection".
"""

from __future__ import annotations

from src.history import history_service
from src.history.models import ChangeType
from src.monitoring import removal, significance
from src.monitoring.base_detector import EventDetector, MonitoringDetectionContext
from src.monitoring.deduplication import make_dedup_key
from src.monitoring.metadata import EventDetectorMetadata
from src.monitoring.models import MonitoringEvent, MonitoringEventType
from src.monitoring.registry import register_event_detector
from src.storage import apartment_repository

# Matches `ranking_v2/rules/availability_rules.py`'s own `_AVAILABLE_STATUSES`
# convention (that constant is module-private there, so this is a small,
# intentional duplication of a one-item set rather than importing a private name).
_AVAILABLE_STATUSES = {"available"}


class ApartmentChangeDetector(EventDetector):
    detector_id = "apartment_change"

    def metadata(self) -> EventDetectorMetadata:
        return EventDetectorMetadata(
            detector_id=self.detector_id, display_name="Apartment Change Detector",
            description=(
                "New matches, price/availability changes, listing detail updates, and "
                "removal-threshold tracking — built on SearchComparison and Apartment History."
            ),
            event_types=(
                MonitoringEventType.NEW_MATCH, MonitoringEventType.NEW_LISTING,
                MonitoringEventType.PRICE_DECREASED, MonitoringEventType.PRICE_INCREASED,
                MonitoringEventType.AVAILABILITY_CHANGED, MonitoringEventType.BECAME_AVAILABLE,
                MonitoringEventType.NO_LONGER_AVAILABLE, MonitoringEventType.AVAILABILITY_CONFIRMED,
                MonitoringEventType.LISTING_REMOVED, MonitoringEventType.LISTING_RETURNED,
                MonitoringEventType.LISTING_UPDATED, MonitoringEventType.IMAGES_CHANGED,
                MonitoringEventType.DESCRIPTION_CHANGED,
            ),
        )

    def detect(self, context: MonitoringDetectionContext) -> list[MonitoringEvent]:
        events: list[MonitoringEvent] = []
        comparison = context.search_comparison

        returned_ids = self._compute_returned_ids(context) if comparison is not None else set()

        if comparison is not None:
            events.extend(self._new_apartment_events(context, comparison, exclude_ids=returned_ids))
            events.extend(self._returned_events(context, returned_ids))
            events.extend(self._price_events(context, comparison))
            events.extend(self._availability_events(context, comparison))
            events.extend(self._listing_update_events(context, comparison))

        events.extend(self._removal_events(context))
        return events

    # ------------------------------------------------------------------ #

    def _compute_returned_ids(self, context: MonitoringDetectionContext) -> set[str]:
        """An apartment is "returned" (not merely "new") when it's observed
        this run but was absent from at least one immediately-preceding run —
        "Do not mark a listing removed after one failed observation" cuts both
        ways: a listing that was only briefly missing and comes back is a
        distinct, more informative event than a generic NEW_MATCH.

        `consecutive_absences() == len(prior_observed_apartment_sets)` means the
        apartment was never found in *any* prior run's observed set at all —
        that's a brand-new apartment with no observation history, not one
        that went missing and came back. Only a count strictly less than the
        full history length means the scan actually found (and broke on) a
        real prior presence.
        """
        prior_sets = context.prior_observed_apartment_sets
        if not prior_sets:
            return set()
        immediately_previous = prior_sets[0]
        returned = set()
        for apartment_id in context.current_observed_apartment_ids:
            if apartment_id in immediately_previous:
                continue
            absences = removal.consecutive_absences(prior_sets, apartment_id)
            if 0 < absences < len(prior_sets):
                returned.add(apartment_id)
        return returned

    def _new_apartment_events(self, context, comparison, *, exclude_ids: set[str]) -> list[MonitoringEvent]:
        events = []
        for apartment_id in comparison.new_apartment_ids:
            if apartment_id in exclude_ids:
                continue
            apartment = apartment_repository.get_apartment(context.conn, apartment_id)
            if apartment is None:
                continue
            is_first_ever = apartment.first_seen_at == apartment.last_seen_at
            event_type = MonitoringEventType.NEW_LISTING if is_first_ever else MonitoringEventType.NEW_MATCH
            sig = significance.new_match_significance(is_first_ever_listing=is_first_ever)
            new_value = {"title": apartment.title, "price": apartment.current_price}
            event = self._build_event(
                context, apartment_id=apartment_id, platform_id=apartment.platform_id, event_type=event_type,
                significance_value=sig, new_value=new_value,
                explanation=("New listing: " if is_first_ever else "Existing apartment newly matches this saved search: ") + apartment.title,
            )
            events.append(event)
        return events

    def _returned_events(self, context, returned_ids: set[str]) -> list[MonitoringEvent]:
        events = []
        for apartment_id in returned_ids:
            apartment = apartment_repository.get_apartment(context.conn, apartment_id)
            if apartment is None:
                continue
            event = self._build_event(
                context, apartment_id=apartment_id, platform_id=apartment.platform_id,
                event_type=MonitoringEventType.LISTING_RETURNED, significance_value=significance.LISTING_RETURNED,
                new_value={"title": apartment.title}, explanation=f"Previously missing listing reappeared: {apartment.title}",
            )
            events.append(event)
            if apartment.current_status in _AVAILABLE_STATUSES:
                confirmed = self._build_event(
                    context, apartment_id=apartment_id, platform_id=apartment.platform_id,
                    event_type=MonitoringEventType.AVAILABILITY_CONFIRMED, significance_value=significance.availability_change_significance(False),
                    new_value={"status": apartment.current_status}, explanation=f"Availability confirmed after reappearing: {apartment.title}",
                )
                events.append(confirmed)
        return events

    def _price_events(self, context, comparison) -> list[MonitoringEvent]:
        events = []
        for change in comparison.price_changes:
            if change.old_price is None or change.new_price is None or change.old_price == change.new_price:
                continue
            sig = significance.price_change_significance(change.old_price, change.new_price)
            if sig < context.version.monitoring_policy.minimum_change_significance:
                continue
            apartment = apartment_repository.get_apartment(context.conn, change.apartment_id)
            event_type = MonitoringEventType.PRICE_DECREASED if change.new_price < change.old_price else MonitoringEventType.PRICE_INCREASED
            event = self._build_event(
                context, apartment_id=change.apartment_id, platform_id=apartment.platform_id if apartment else None,
                event_type=event_type, significance_value=sig,
                old_value={"price": change.old_price}, new_value={"price": change.new_price},
                explanation=f"Price {'decreased' if event_type == MonitoringEventType.PRICE_DECREASED else 'increased'}: {change.old_price} -> {change.new_price}",
            )
            events.append(event)
        return events

    def _availability_events(self, context, comparison) -> list[MonitoringEvent]:
        events = []
        for change in comparison.availability_changes:
            if change.old_status == change.new_status:
                continue
            old_available = (change.old_status or "") in _AVAILABLE_STATUSES
            new_available = (change.new_status or "") in _AVAILABLE_STATUSES
            flipped = old_available != new_available
            if flipped and new_available:
                event_type = MonitoringEventType.BECAME_AVAILABLE
            elif flipped and not new_available:
                event_type = MonitoringEventType.NO_LONGER_AVAILABLE
            else:
                event_type = MonitoringEventType.AVAILABILITY_CHANGED
            apartment = apartment_repository.get_apartment(context.conn, change.apartment_id)
            event = self._build_event(
                context, apartment_id=change.apartment_id, platform_id=apartment.platform_id if apartment else None,
                event_type=event_type, significance_value=significance.availability_change_significance(flipped),
                old_value={"status": change.old_status}, new_value={"status": change.new_status},
                explanation=f"Availability changed: {change.old_status} -> {change.new_status}",
            )
            events.append(event)
        return events

    def _listing_update_events(self, context, comparison) -> list[MonitoringEvent]:
        events = []
        existing_ids = context.current_observed_apartment_ids - set(comparison.new_apartment_ids)
        for apartment_id in existing_ids:
            changes_this_run = [
                c for c in history_service.change_timeline(context.conn, apartment_id) if c.search_id == context.run.search_id
            ]
            if not changes_this_run:
                continue
            has_image_change = any(c.change_type in (ChangeType.IMAGE_ADDED, ChangeType.IMAGE_REMOVED) for c in changes_this_run)
            has_description_change = any(c.change_type == ChangeType.DESCRIPTION_CHANGED for c in changes_this_run)
            has_title_change = any(c.change_type == ChangeType.TITLE_CHANGED for c in changes_this_run)

            if has_image_change:
                event = self._build_event(
                    context, apartment_id=apartment_id, event_type=MonitoringEventType.IMAGES_CHANGED,
                    significance_value=significance.LISTING_UPDATED, explanation="Listing images changed",
                )
                events.append(event)
            if has_description_change:
                event = self._build_event(
                    context, apartment_id=apartment_id, event_type=MonitoringEventType.DESCRIPTION_CHANGED,
                    significance_value=significance.LISTING_UPDATED, explanation="Listing description changed",
                )
                events.append(event)
            if has_title_change and not (has_image_change or has_description_change):
                event = self._build_event(
                    context, apartment_id=apartment_id, event_type=MonitoringEventType.LISTING_UPDATED,
                    significance_value=significance.LISTING_UPDATED, explanation="Listing title changed",
                )
                events.append(event)
        return events

    def _removal_events(self, context: MonitoringDetectionContext) -> list[MonitoringEvent]:
        events = []
        policy = context.version.monitoring_policy
        all_prior_ids: set[str] = set()
        for observed in context.prior_observed_apartment_sets:
            all_prior_ids |= observed
        missing_ids = all_prior_ids - context.current_observed_apartment_ids

        for apartment_id in missing_ids:
            misses = removal.consecutive_absences(context.prior_observed_apartment_sets, apartment_id) + 1
            if not removal.just_crossed_removal_threshold(misses, policy):
                continue
            apartment = apartment_repository.get_apartment(context.conn, apartment_id)
            event = self._build_event(
                context, apartment_id=apartment_id, platform_id=apartment.platform_id if apartment else None,
                event_type=MonitoringEventType.LISTING_REMOVED, significance_value=significance.LISTING_REMOVED,
                explanation=f"Listing missing from {misses} consecutive successful searches — confirmed removed",
                evidence={"consecutive_absences": misses, "removed_listing_threshold": policy.removed_listing_threshold},
            )
            events.append(event)
        return events

    def _build_event(
        self, context: MonitoringDetectionContext, *, apartment_id: str, event_type: str, significance_value: float,
        explanation: str, platform_id: str | None = None, old_value: dict | None = None, new_value: dict | None = None,
        evidence: dict | None = None,
    ) -> MonitoringEvent:
        dedup_key = make_dedup_key(context.saved_search.saved_search_id, apartment_id, event_type)
        return MonitoringEvent(
            saved_search_id=context.saved_search.saved_search_id, saved_search_version=context.version.version,
            monitoring_run_id=context.run.monitoring_run_id, search_id=context.run.search_id,
            apartment_id=apartment_id, platform_id=platform_id, event_type=event_type,
            severity=significance.severity_for_significance(significance_value), significance=significance_value,
            old_value=old_value, new_value=new_value, explanation=explanation,
            evidence=evidence or {"apartment_id": apartment_id}, detected_at=context.now, dedup_key=dedup_key,
        )


register_event_detector(ApartmentChangeDetector())
