"""`NotificationEngine` — preference lifecycle (create/update/enable/disable)
and the mission's own delivery workflow: load undelivered eligible
`MonitoringEvent`s -> resolve preference version -> evaluate eligibility ->
apply quiet hours/rate limits -> choose immediate-or-digest -> generate a
versioned message -> resolve channels -> attempt delivery per channel
independently -> record attempts -> mark status -> update statistics -> leave
`MonitoringEvent`s untouched. See docs/31_Notification_Delivery.md
"Architecture"/"Delivery Workflow".

Every channel (`NotificationChannel`) and template (`NotificationTemplate`) is
consumed exactly as published — this module only adds orchestration,
eligibility, and retry/rate-limit/quiet-hours policy on top.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from src.monitoring import service as monitoring_service
from src.notifications import eligibility as eligibility_module
from src.notifications import quiet_hours, rate_limiting, retry, service
from src.notifications.base_template import TemplateContext
from src.notifications.exceptions import NotificationConfigurationError, NotificationValidationError
from src.notifications.factory import NotificationChannelFactory
from src.notifications.models import (
    NotificationAttempt,
    NotificationBatch,
    NotificationConfiguration,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationDigest,
    NotificationMessage,
    NotificationPolicy,
    NotificationPreference,
    NotificationPreferenceVersion,
)
from src.notifications.template_registry import NotificationTemplateRegistry
from src.storage.database import Database

_DIGEST_LOOKBACK = {"hourly": timedelta(hours=1), "daily": timedelta(days=1), "weekly": timedelta(days=7)}


def _digest_template_for_frequency(frequency: str | None):
    """`daily_digest`/`weekly_digest` are the two registered digest templates;
    hourly and manual digests reuse `daily_digest`'s own rendering (identical
    grouping/ordering logic, just a different `context.frequency` label) —
    see `templates/digest_templates.py`'s own docstring for why a third/fourth
    template class isn't needed.
    """
    name = f"{frequency}_digest" if frequency in ("daily", "weekly") else "daily_digest"
    return NotificationTemplateRegistry.get(name)


class NotificationEngine:
    def __init__(self, configuration: NotificationConfiguration | None = None) -> None:
        self._configuration = configuration or NotificationConfiguration()

    # ------------------------------------------------------------------ #
    # preference lifecycle
    # ------------------------------------------------------------------ #

    def create_preference(
        self, db: Database, profile_id: str, *, saved_search_id: str | None = None, enabled_channels: list[str] | None = None,
        event_types: list[str] | None = None, immediate_event_types: list[str] | None = None,
        digest_event_types: list[str] | None = None, minimum_severity: str | None = None, minimum_significance: float = 0.0,
        digest_frequency: str | None = None, quiet_hours_start: str | None = None, quiet_hours_end: str | None = None,
        timezone_name: str = "UTC", max_per_hour: int | None = None, max_per_day: int | None = None,
        include_images: bool = True, include_original_urls: bool = True, include_ranking_explanation: bool = True,
        include_geo_summary: bool = True, include_preference_explanation: bool = True, include_report_links: bool = True,
        language: str = "en", format: str = "text", metadata: dict | None = None, now: datetime | None = None,
    ) -> NotificationPreference:
        if not profile_id:
            raise NotificationValidationError("NotificationPreference.profile_id is required")
        if not enabled_channels:
            raise NotificationValidationError("At least one enabled channel is required")

        now = now or datetime.now(timezone.utc)
        preference_id = str(uuid.uuid4())
        preference = NotificationPreference(
            preference_id=preference_id, profile_id=profile_id, current_version=1, enabled=True, created_at=now,
            updated_at=now, saved_search_id=saved_search_id,
        )
        version = NotificationPreferenceVersion(
            preference_id=preference_id, version=1, enabled_channels=enabled_channels, event_types=event_types or [],
            immediate_event_types=immediate_event_types or [], digest_event_types=digest_event_types or [],
            timezone=timezone_name, include_images=include_images, include_original_urls=include_original_urls,
            include_ranking_explanation=include_ranking_explanation, include_geo_summary=include_geo_summary,
            include_preference_explanation=include_preference_explanation, include_report_links=include_report_links,
            language=language, format=format, metadata=metadata or {}, created_at=now, minimum_severity=minimum_severity,
            minimum_significance=minimum_significance, digest_frequency=digest_frequency,
            quiet_hours_start=quiet_hours_start, quiet_hours_end=quiet_hours_end, max_per_hour=max_per_hour,
            max_per_day=max_per_day,
        )
        with db.transaction() as conn:
            service.record_preference(conn, preference)
            service.record_preference_version(conn, version)
        return preference

    def update_preference(self, db: Database, preference_id: str, *, now: datetime | None = None, **overrides) -> NotificationPreferenceVersion:
        """Creates a new immutable version — "Never overwrite preferences"
        (the mission's own words).
        """
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            preference = service.get_preference(conn, preference_id)
            if preference is None:
                raise NotificationValidationError(f"No such notification preference {preference_id!r}")
            current = service.get_latest_preference_version(conn, preference_id)
            if current is None:
                raise NotificationConfigurationError(f"Preference {preference_id!r} has no version {preference.current_version}")

            fields = {
                "enabled_channels": current.enabled_channels, "event_types": current.event_types,
                "immediate_event_types": current.immediate_event_types, "digest_event_types": current.digest_event_types,
                "timezone": current.timezone, "include_images": current.include_images,
                "include_original_urls": current.include_original_urls,
                "include_ranking_explanation": current.include_ranking_explanation,
                "include_geo_summary": current.include_geo_summary,
                "include_preference_explanation": current.include_preference_explanation,
                "include_report_links": current.include_report_links, "language": current.language,
                "format": current.format, "metadata": current.metadata, "minimum_severity": current.minimum_severity,
                "minimum_significance": current.minimum_significance, "digest_frequency": current.digest_frequency,
                "quiet_hours_start": current.quiet_hours_start, "quiet_hours_end": current.quiet_hours_end,
                "max_per_hour": current.max_per_hour, "max_per_day": current.max_per_day,
            }
            fields.update(overrides)

            new_version_number = preference.current_version + 1
            new_version = NotificationPreferenceVersion(preference_id=preference_id, version=new_version_number, created_at=now, **fields)
            service.record_preference_version(conn, new_version)

            preference.current_version = new_version_number
            preference.updated_at = now
            service.update_preference(conn, preference)

        return new_version

    def set_enabled(self, db: Database, preference_id: str, enabled: bool, *, now: datetime | None = None) -> NotificationPreference:
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            preference = service.get_preference(conn, preference_id)
            if preference is None:
                raise NotificationValidationError(f"No such notification preference {preference_id!r}")
            preference.enabled = enabled
            preference.updated_at = now
            service.update_preference(conn, preference)
        return preference

    # ------------------------------------------------------------------ #
    # delivery workflow — immediate
    # ------------------------------------------------------------------ #

    def process_pending_deliveries(self, db: Database, *, now: datetime | None = None) -> NotificationBatch:
        now = now or datetime.now(timezone.utc)
        batch = NotificationBatch(batch_type="immediate", started_at=now)

        with db.transaction() as conn:
            service.sync_registered_templates(conn, now)
            service.record_batch(conn, batch)

            candidate_events = [e for e in monitoring_service.get_unacknowledged_events(conn) if not service.get_delivery_ids_for_event(conn, e.event_id)]

            for event in candidate_events:
                for preference in self._applicable_preferences(conn, event):
                    version = service.get_latest_preference_version(conn, preference.preference_id)
                    if version is None:
                        continue

                    eligibility = eligibility_module.evaluate_event(event, preference, version)
                    if not eligibility.eligible or eligibility.is_digest_only:
                        continue  # digest-only events are handled by process_due_digests()

                    dedup_key = f"{preference.preference_id}:{event.event_id}"
                    if service.get_delivery_by_idempotency_key(conn, dedup_key) is not None:
                        continue  # already created for this preference+event — idempotent

                    channels = self._filter_rate_limited(conn, preference.profile_id, eligibility.eligible_channels, version, now)
                    deferred = quiet_hours.is_in_quiet_hours(version, now) and event.severity != "critical"

                    delivery = NotificationDelivery(
                        profile_id=preference.profile_id, saved_search_id=event.saved_search_id,
                        saved_search_version=event.saved_search_version, preference_id=preference.preference_id,
                        preference_version=version.version, is_digest=False,
                        status=NotificationDeliveryStatus.SUPPRESSED if (deferred or not channels) else NotificationDeliveryStatus.PENDING,
                        channels=channels or eligibility.eligible_channels, event_ids=[event.event_id], dedup_key=dedup_key,
                        idempotency_key=dedup_key, created_at=now, batch_id=batch.batch_id,
                    )
                    if deferred:
                        delivery.next_attempt_at = quiet_hours.next_permitted_time(version, now)
                        delivery.notes = "Deferred: quiet hours"
                    elif not channels:
                        delivery.notes = "Suppressed: rate limit reached for every eligible channel"
                    service.record_delivery(conn, delivery)

                    batch.deliveries_attempted += 1
                    if delivery.status is NotificationDeliveryStatus.SUPPRESSED:
                        continue

                    template = NotificationTemplateRegistry.for_event_type(event.event_type)
                    if template is None:
                        continue
                    context = TemplateContext(conn=conn, events=[event], preference_version=version, now=now, saved_search_name=self._saved_search_name(conn, event.saved_search_id))
                    rendered = template.render(context)

                    self._attempt_delivery(conn, delivery, rendered, template, version, now)
                    if delivery.status is NotificationDeliveryStatus.DELIVERED:
                        batch.deliveries_succeeded += 1
                    elif delivery.status in (NotificationDeliveryStatus.FAILED, NotificationDeliveryStatus.PARTIALLY_DELIVERED):
                        batch.deliveries_failed += 1

            batch.completed_at = datetime.now(timezone.utc)
            service.update_batch(conn, batch)

        return batch

    def retry_due_failures(self, db: Database, *, now: datetime | None = None) -> NotificationBatch:
        now = now or datetime.now(timezone.utc)
        batch = NotificationBatch(batch_type="retry", started_at=now)

        with db.transaction() as conn:
            service.record_batch(conn, batch)
            due = service.get_due_retries(conn, now)

            for delivery in due:
                preference = service.get_preference(conn, delivery.preference_id)
                version = service.get_preference_version(conn, delivery.preference_id, delivery.preference_version)
                if preference is None or version is None:
                    continue

                already_delivered_channels = {a.channel for a in service.get_attempts_for_delivery(conn, delivery.delivery_id) if a.status == "delivered"}
                pending_channels = [c for c in delivery.channels if c not in already_delivered_channels]
                if not pending_channels:
                    continue

                events = [monitoring_service.get_event(conn, event_id) for event_id in delivery.event_ids]
                events = [e for e in events if e is not None]
                if not events:
                    continue

                if delivery.is_digest:
                    digest = service.get_digest_for_delivery(conn, delivery.delivery_id)
                    template = _digest_template_for_frequency(digest.frequency) if digest else None
                    context = TemplateContext(conn=conn, events=events, preference_version=version, now=now, frequency=digest.frequency if digest else None, period_start=digest.period_start if digest else None, period_end=digest.period_end if digest else None)
                else:
                    template = NotificationTemplateRegistry.for_event_type(events[0].event_type)
                    context = TemplateContext(conn=conn, events=events, preference_version=version, now=now, saved_search_name=self._saved_search_name(conn, delivery.saved_search_id))
                if template is None:
                    continue
                rendered = template.render(context)

                batch.deliveries_attempted += 1
                self._attempt_delivery(conn, delivery, rendered, template, version, now, channels_to_try=pending_channels)
                if delivery.status is NotificationDeliveryStatus.DELIVERED:
                    batch.deliveries_succeeded += 1
                elif delivery.status in (NotificationDeliveryStatus.FAILED, NotificationDeliveryStatus.PARTIALLY_DELIVERED):
                    batch.deliveries_failed += 1

            batch.completed_at = datetime.now(timezone.utc)
            service.update_batch(conn, batch)

        return batch

    # ------------------------------------------------------------------ #
    # digest delivery
    # ------------------------------------------------------------------ #

    def process_due_digests(self, db: Database, *, now: datetime | None = None) -> NotificationBatch:
        from src.notifications import scheduling

        now = now or datetime.now(timezone.utc)
        batch = NotificationBatch(batch_type="digest", started_at=now)

        with db.transaction() as conn:
            service.sync_registered_templates(conn, now)
            service.record_batch(conn, batch)

            for preference in service.get_all_preferences(conn, enabled_only=True):
                version = service.get_latest_preference_version(conn, preference.preference_id)
                if version is None or not version.digest_frequency or version.digest_frequency == "manual":
                    continue
                if not scheduling.is_digest_due(conn, preference.preference_id, version, now):
                    continue
                self._generate_one_digest(conn, batch, preference, version, now)

            batch.completed_at = datetime.now(timezone.utc)
            service.update_batch(conn, batch)

        return batch

    def generate_digest(self, db: Database, preference_id: str, *, now: datetime | None = None) -> NotificationDelivery | None:
        """Manual digest generation — "manual digest" (the mission's own
        words) — bypasses the due-time check `process_due_digests()` applies.
        """
        now = now or datetime.now(timezone.utc)
        batch = NotificationBatch(batch_type="digest", started_at=now)
        with db.transaction() as conn:
            service.sync_registered_templates(conn, now)
            service.record_batch(conn, batch)
            preference = service.get_preference(conn, preference_id)
            version = service.get_latest_preference_version(conn, preference_id) if preference else None
            if preference is None or version is None:
                raise NotificationValidationError(f"No such notification preference {preference_id!r}")
            delivery = self._generate_one_digest(conn, batch, preference, version, now, frequency_override=version.digest_frequency or "manual")
            batch.completed_at = datetime.now(timezone.utc)
            service.update_batch(conn, batch)
        return delivery

    def _generate_one_digest(self, conn, batch: NotificationBatch, preference: NotificationPreference, version: NotificationPreferenceVersion, now: datetime, *, frequency_override: str | None = None) -> NotificationDelivery | None:
        from src.notifications import scheduling

        frequency = frequency_override or version.digest_frequency
        latest = service.get_latest_digest_for_preference(conn, preference.preference_id)
        period_start = latest.period_end if latest else (now - _DIGEST_LOOKBACK.get(frequency, _DIGEST_LOOKBACK["daily"]))
        period_end = now

        events = self._events_in_window(conn, preference, version, period_start, period_end)
        if not events:
            return None

        channels = self._filter_rate_limited(conn, preference.profile_id, [c for c in version.enabled_channels if self._channel_enabled(c)], version, now)
        if not channels:
            return None

        dedup_key = f"{preference.preference_id}:digest:{period_start.isoformat()}:{period_end.isoformat()}"
        delivery = NotificationDelivery(
            profile_id=preference.profile_id, saved_search_id=preference.saved_search_id, preference_id=preference.preference_id,
            preference_version=version.version, is_digest=True, status=NotificationDeliveryStatus.PENDING, channels=channels,
            event_ids=[e.event_id for e in events], dedup_key=dedup_key, idempotency_key=dedup_key, created_at=now, batch_id=batch.batch_id,
        )
        service.record_delivery(conn, delivery)
        service.record_digest(conn, NotificationDigest(delivery_id=delivery.delivery_id, frequency=frequency, period_start=period_start, period_end=period_end, event_ids=delivery.event_ids, generated_at=now))

        template = _digest_template_for_frequency(frequency)
        context = TemplateContext(conn=conn, events=events, preference_version=version, now=now, frequency=frequency, period_start=period_start, period_end=period_end, saved_search_name=self._saved_search_name(conn, preference.saved_search_id))
        rendered = template.render(context)

        batch.deliveries_attempted += 1
        self._attempt_delivery(conn, delivery, rendered, template, version, now)
        if delivery.status is NotificationDeliveryStatus.DELIVERED:
            batch.deliveries_succeeded += 1
        elif delivery.status in (NotificationDeliveryStatus.FAILED, NotificationDeliveryStatus.PARTIALLY_DELIVERED):
            batch.deliveries_failed += 1
        return delivery

    def _events_in_window(self, conn, preference: NotificationPreference, version: NotificationPreferenceVersion, period_start: datetime, period_end: datetime) -> list:
        events = []
        seen_ids: set[str] = set()
        if preference.saved_search_id:
            candidates = monitoring_service.get_events_for_saved_search(conn, preference.saved_search_id)
        else:
            candidates = monitoring_service.get_unacknowledged_events(conn)
        for event in candidates:
            if event.event_id in seen_ids or event.acknowledged or not event.notification_eligible:
                continue
            if not (period_start <= event.detected_at <= period_end):
                continue
            if version.event_types and event.event_type not in version.event_types:
                continue
            if event.significance < version.minimum_significance:
                continue
            if version.digest_event_types and event.event_type not in version.digest_event_types and event.event_type in version.immediate_event_types:
                continue  # already handled (or will be) by the immediate path
            if service.get_delivery_ids_for_event(conn, event.event_id):
                continue  # already included in a prior delivery — no duplicate membership
            events.append(event)
            seen_ids.add(event.event_id)
        return events

    # ------------------------------------------------------------------ #
    # preview / test / acknowledge
    # ------------------------------------------------------------------ #

    def preview(self, db: Database, preference_id: str, event_ids: list[str], channel_name: str, *, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            preference = service.get_preference(conn, preference_id)
            version = service.get_latest_preference_version(conn, preference_id) if preference else None
            if preference is None or version is None:
                raise NotificationValidationError(f"No such notification preference {preference_id!r}")
            events = [monitoring_service.get_event(conn, event_id) for event_id in event_ids]
            events = [e for e in events if e is not None]
            if not events:
                raise NotificationValidationError("No valid monitoring events found for preview")
            template = NotificationTemplateRegistry.for_event_type(events[0].event_type) if len(events) == 1 else NotificationTemplateRegistry.get("daily_digest")
            context = TemplateContext(conn=conn, events=events, preference_version=version, now=now)
            rendered = template.render(context)
            channel = NotificationChannelFactory.get(channel_name)
            message = self._build_message("preview", rendered, template, channel_name, version, now, [e.event_id for e in events])
            return channel.preview(message)

    def send_test_notification(self, db: Database, preference_id: str, channel_name: str, *, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            version = service.get_latest_preference_version(conn, preference_id)
            if version is None:
                raise NotificationValidationError(f"No such notification preference {preference_id!r}")
            channel = NotificationChannelFactory.get(channel_name)
            message = NotificationMessage(
                delivery_id="test", profile_id="test", event_ids=[], channel=channel_name,
                body_text="This is a test notification from the Rental Agent Notification Delivery Engine.",
                template_name="test", template_version=1, language=version.language, generated_at=now, subject="Test Notification",
            )
            return channel.send(message)

    def acknowledge(self, db: Database, delivery_id: str, *, acknowledged_by: str | None = None, note: str | None = None, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            service.acknowledge_delivery(conn, delivery_id, acknowledged_by=acknowledged_by, note=note, now=now)

    def retry_delivery_now(self, db: Database, delivery_id: str, *, now: datetime | None = None) -> NotificationDelivery:
        """Retries one specific delivery on demand, regardless of
        `next_attempt_at` — the CLI's own `retry-delivery` command. Reuses
        exactly the same per-channel, idempotent attempt logic
        `retry_due_failures()` applies in bulk.
        """
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            delivery = service.get_delivery(conn, delivery_id)
            if delivery is None:
                raise NotificationValidationError(f"No such notification delivery {delivery_id!r}")
            version = service.get_preference_version(conn, delivery.preference_id, delivery.preference_version)
            if version is None:
                raise NotificationConfigurationError(f"Delivery {delivery_id!r} references a missing preference version")

            already_delivered = {a.channel for a in service.get_attempts_for_delivery(conn, delivery.delivery_id) if a.status == "delivered"}
            pending_channels = [c for c in delivery.channels if c not in already_delivered]
            if not pending_channels:
                return delivery

            events = [e for e in (monitoring_service.get_event(conn, event_id) for event_id in delivery.event_ids) if e is not None]
            if not events:
                raise NotificationValidationError(f"Delivery {delivery_id!r} references no existing monitoring events")

            if delivery.is_digest:
                digest = service.get_digest_for_delivery(conn, delivery.delivery_id)
                template = _digest_template_for_frequency(digest.frequency if digest else None)
                context = TemplateContext(conn=conn, events=events, preference_version=version, now=now, frequency=digest.frequency if digest else None, period_start=digest.period_start if digest else None, period_end=digest.period_end if digest else None)
            else:
                template = NotificationTemplateRegistry.for_event_type(events[0].event_type)
                context = TemplateContext(conn=conn, events=events, preference_version=version, now=now, saved_search_name=self._saved_search_name(conn, delivery.saved_search_id))
            if template is None:
                raise NotificationConfigurationError(f"No template registered for delivery {delivery_id!r}")
            rendered = template.render(context)

            self._attempt_delivery(conn, delivery, rendered, template, version, now, channels_to_try=pending_channels)
            return delivery

    def cancel_delivery(self, db: Database, delivery_id: str, *, now: datetime | None = None) -> NotificationDelivery:
        now = now or datetime.now(timezone.utc)
        with db.transaction() as conn:
            delivery = service.get_delivery(conn, delivery_id)
            if delivery is None:
                raise NotificationValidationError(f"No such notification delivery {delivery_id!r}")
            delivery.status = NotificationDeliveryStatus.CANCELLED
            delivery.next_attempt_at = None
            service.update_delivery(conn, delivery)
            return delivery

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _applicable_preferences(self, conn, event) -> list[NotificationPreference]:
        saved_search = monitoring_service.get_saved_search(conn, event.saved_search_id) if event.saved_search_id else None
        profile_id = saved_search.profile_id if saved_search else None

        matches = []
        for preference in service.get_all_preferences(conn, enabled_only=True):
            if preference.saved_search_id == event.saved_search_id:
                matches.append(preference)
            elif preference.saved_search_id is None and profile_id is not None and preference.profile_id == profile_id:
                matches.append(preference)
        return matches

    def _filter_rate_limited(self, conn, profile_id: str, channels: list[str], version: NotificationPreferenceVersion, now: datetime) -> list[str]:
        return [c for c in channels if not rate_limiting.is_rate_limited(conn, profile_id, c, version, now)]

    def _channel_enabled(self, channel_name: str) -> bool:
        from src.notifications.registry import NotificationChannelRegistry

        return NotificationChannelRegistry.is_registered(channel_name) and NotificationChannelRegistry.get(channel_name).is_enabled()

    def _saved_search_name(self, conn, saved_search_id: str | None) -> str | None:
        if not saved_search_id:
            return None
        saved_search = monitoring_service.get_saved_search(conn, saved_search_id)
        return saved_search.name if saved_search else None

    def _build_message(self, delivery_id: str, rendered, template, channel_name: str, version: NotificationPreferenceVersion, now: datetime, event_ids: list[str]) -> NotificationMessage:
        return NotificationMessage(
            delivery_id=delivery_id, profile_id="", event_ids=event_ids, channel=channel_name, body_text=rendered.body_text,
            template_name=template.template_name, template_version=template.version, language=version.language,
            generated_at=now, subject=rendered.subject, body_html=rendered.body_html if version.format == "html" else None,
            original_listing_urls=rendered.original_listing_urls, report_links=rendered.report_links,
        )

    def _attempt_delivery(self, conn, delivery: NotificationDelivery, rendered, template, version: NotificationPreferenceVersion, now: datetime, *, channels_to_try: list[str] | None = None) -> None:
        policy: NotificationPolicy = self._configuration.default_policy
        channels_to_try = channels_to_try or delivery.channels
        any_success = False
        any_retryable_failure = False
        any_non_retryable_failure = False

        for channel_name in channels_to_try:
            channel = NotificationChannelFactory.get(channel_name)
            message = NotificationMessage(
                delivery_id=delivery.delivery_id, profile_id=delivery.profile_id, event_ids=delivery.event_ids,
                channel=channel_name, body_text=rendered.body_text, template_name=template.template_name,
                template_version=template.version, language=version.language, generated_at=now, subject=rendered.subject,
                body_html=rendered.body_html if version.format == "html" else None,
                original_listing_urls=rendered.original_listing_urls, report_links=rendered.report_links,
                metadata={"attempt_number": delivery.attempt_count + 1},
            )
            service.record_message(conn, message)

            result = channel.send(message)
            service.record_attempt(conn, NotificationAttempt(
                delivery_id=delivery.delivery_id, channel=channel_name, attempt_number=delivery.attempt_count + 1,
                status="delivered" if result.success else "failed", attempted_at=now, error=result.error,
                error_category=result.error_category, duration_ms=result.duration_ms,
            ))
            service.record_channel_health_observation(conn, channel_name, result.success, now, error=result.error, duration_ms=result.duration_ms)

            if result.success:
                any_success = True
                rate_limiting.record_send(conn, delivery.profile_id, channel_name, now)
            elif retry.is_retryable(result.error_category, policy):
                any_retryable_failure = True
            else:
                any_non_retryable_failure = True

        delivery.attempt_count += 1

        if any_success and not (any_retryable_failure or any_non_retryable_failure):
            delivery.status = NotificationDeliveryStatus.DELIVERED
            delivery.next_attempt_at = None
        elif any_success:
            delivery.status = NotificationDeliveryStatus.PARTIALLY_DELIVERED
            if any_retryable_failure and not retry.should_dead_letter(delivery.attempt_count, policy):
                delivery.next_attempt_at = retry.compute_next_attempt_at(delivery.attempt_count, policy, now)
            else:
                delivery.next_attempt_at = None
        elif any_retryable_failure and not retry.should_dead_letter(delivery.attempt_count, policy):
            delivery.status = NotificationDeliveryStatus.RETRY_SCHEDULED
            delivery.next_attempt_at = retry.compute_next_attempt_at(delivery.attempt_count, policy, now)
        else:
            delivery.status = NotificationDeliveryStatus.FAILED
            delivery.next_attempt_at = None

        service.update_delivery(conn, delivery)
