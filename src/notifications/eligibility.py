"""Deterministic, explainable event eligibility. See
docs/31_Notification_Delivery.md "Eligibility" — "Eligibility decisions must
be deterministic and explainable" (the mission's own words): every ineligible
outcome names its exact reason, never a bare `False`.

Quiet hours and rate limiting are deliberately NOT evaluated here — they're
time-dependent, deferral-capable decisions (see `quiet_hours.py`/
`rate_limiting.py`), applied by `NotificationEngine` as its own explicit
workflow step, right after this one, exactly matching the mission's own
workflow diagram ("Evaluate eligibility" -> "Apply quiet hours and rate
limits" as two separate steps).
"""

from __future__ import annotations

from src.monitoring.models import MonitoringEvent
from src.notifications.models import NotificationEligibility, NotificationPreference, NotificationPreferenceVersion
from src.notifications.registry import NotificationChannelRegistry

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def evaluate_event(
    event: MonitoringEvent, preference: NotificationPreference, preference_version: NotificationPreferenceVersion,
) -> NotificationEligibility:
    if not preference.enabled:
        return NotificationEligibility(event_id=event.event_id, eligible=False, ineligible_reasons={"*": "notification preference is disabled"})

    if event.acknowledged:
        return NotificationEligibility(event_id=event.event_id, eligible=False, ineligible_reasons={"*": "monitoring event already acknowledged"})

    if not event.notification_eligible:
        return NotificationEligibility(event_id=event.event_id, eligible=False, ineligible_reasons={"*": "event marked notification_eligible=False"})

    if preference_version.event_types and event.event_type not in preference_version.event_types:
        return NotificationEligibility(
            event_id=event.event_id, eligible=False,
            ineligible_reasons={"*": f"event_type {event.event_type!r} is not in this preference's opted-in event types"},
        )

    if preference_version.minimum_severity and _SEVERITY_RANK.get(event.severity, 0) < _SEVERITY_RANK.get(preference_version.minimum_severity, 0):
        return NotificationEligibility(
            event_id=event.event_id, eligible=False,
            ineligible_reasons={"*": f"severity {event.severity!r} is below minimum_severity {preference_version.minimum_severity!r}"},
        )

    if event.significance < preference_version.minimum_significance:
        return NotificationEligibility(
            event_id=event.event_id, eligible=False,
            ineligible_reasons={"*": f"significance {event.significance} is below minimum_significance {preference_version.minimum_significance}"},
        )

    channels, reasons = _resolve_channels(preference_version)
    if not channels:
        reasons.setdefault("*", "no enabled channel is both opted-in and currently configured")
        return NotificationEligibility(event_id=event.event_id, eligible=False, ineligible_reasons=reasons)

    is_immediate = event.event_type in preference_version.immediate_event_types
    is_digest_only = not is_immediate and bool(preference_version.digest_frequency)

    return NotificationEligibility(
        event_id=event.event_id, eligible=True, eligible_channels=channels, ineligible_reasons=reasons,
        is_immediate=is_immediate, is_digest_only=is_digest_only,
    )


def _resolve_channels(preference_version: NotificationPreferenceVersion) -> tuple[list[str], dict[str, str]]:
    channels = []
    reasons: dict[str, str] = {}
    for channel_name in preference_version.enabled_channels:
        if not NotificationChannelRegistry.is_registered(channel_name):
            reasons[channel_name] = "channel is not registered"
            continue
        channel = NotificationChannelRegistry.get(channel_name)
        if not channel.is_enabled():
            reasons[channel_name] = "channel is not currently configured"
            continue
        channels.append(channel_name)
    return channels, reasons


def explain_eligibility(eligibility: NotificationEligibility) -> str:
    if eligibility.eligible:
        kind = "immediate" if eligibility.is_immediate else ("digest-only" if eligibility.is_digest_only else "immediate-or-digest")
        return f"Eligible ({kind}) via channels: {', '.join(eligibility.eligible_channels) or 'none'}"
    reasons = "; ".join(f"{channel}: {reason}" for channel, reason in eligibility.ineligible_reasons.items())
    return f"Ineligible — {reasons or 'no reason recorded'}"


def eligible_channels(eligibility: NotificationEligibility) -> list[str]:
    return eligibility.eligible_channels


def ineligible_reasons(eligibility: NotificationEligibility) -> dict[str, str]:
    return eligibility.ineligible_reasons
