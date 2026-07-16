"""Notification preference create/edit form — see
docs/32_Web_Dashboard.md "Notification Workflow".
"""

from __future__ import annotations

from src.notifications.registry import NotificationChannelRegistry
from src.web.error_handler import WebValidationError
from src.web.forms.validation import (
    parse_checkbox_list,
    parse_optional_float,
    parse_optional_int,
    require_text,
)

_VALID_SEVERITIES = {"info", "warning", "critical"}
_VALID_DIGEST_FREQUENCIES = {"hourly", "daily", "weekly", "manual"}


def parse_notification_preference_form(form) -> dict:
    enabled_channels = parse_checkbox_list(form.getlist("enabled_channels"))
    if not enabled_channels:
        raise WebValidationError("At least one notification channel must be enabled")
    for channel in enabled_channels:
        if not NotificationChannelRegistry.is_registered(channel):
            raise WebValidationError(f"Unknown notification channel {channel!r}")

    minimum_severity = form.get("minimum_severity") or None
    if minimum_severity and minimum_severity not in _VALID_SEVERITIES:
        raise WebValidationError(f"Invalid minimum severity {minimum_severity!r}")

    digest_frequency = form.get("digest_frequency") or None
    if digest_frequency and digest_frequency not in _VALID_DIGEST_FREQUENCIES:
        raise WebValidationError(f"Invalid digest frequency {digest_frequency!r}")

    quiet_start = form.get("quiet_hours_start") or None
    quiet_end = form.get("quiet_hours_end") or None
    for label, value in (("Quiet hours start", quiet_start), ("Quiet hours end", quiet_end)):
        if value and not _is_valid_hhmm(value):
            raise WebValidationError(f"{label} must be in HH:MM format")

    return {
        "enabled_channels": enabled_channels,
        "saved_search_id": form.get("saved_search_id") or None,
        "minimum_severity": minimum_severity,
        "minimum_significance": parse_optional_float(form.get("minimum_significance"), "Minimum significance", minimum=0.0) or 0.0,
        "digest_frequency": digest_frequency,
        "quiet_hours_start": quiet_start,
        "quiet_hours_end": quiet_end,
        "timezone_name": form.get("timezone_name") or "UTC",
        "max_per_hour": parse_optional_int(form.get("max_per_hour"), "Max per hour", minimum=1),
        "max_per_day": parse_optional_int(form.get("max_per_day"), "Max per day", minimum=1),
        "format": form.get("format") or "text",
    }


def _is_valid_hhmm(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2:
        return False
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59
