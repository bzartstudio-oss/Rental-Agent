"""The scheduler interface. See docs/31_Notification_Delivery.md "Scheduler
Interface" — `process_pending_deliveries()`/`process_due_digests()`/
`retry_due_failures()` live on `NotificationEngine` itself (they need the full
engine to actually deliver); this module holds the *timing* questions a
scheduler asks before calling them: `next_delivery_time()`/`next_digest_time()`.

Nothing here loops or sleeps — mirrors `monitoring/scheduling.py`'s own "one
idempotent database operation per call" shape. "Do not implement an
operating-system-specific daemon" (the mission's own words).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from src.notifications import service
from src.notifications.models import NotificationPreferenceVersion

_FREQUENCY_INTERVALS = {"hourly": timedelta(hours=1), "daily": timedelta(days=1), "weekly": timedelta(days=7)}


def next_digest_time(conn: sqlite3.Connection, preference_id: str, preference_version: NotificationPreferenceVersion, now: datetime) -> datetime | None:
    if not preference_version.digest_frequency or preference_version.digest_frequency == "manual":
        return None
    interval = _FREQUENCY_INTERVALS.get(preference_version.digest_frequency)
    if interval is None:
        return None
    latest = service.get_latest_digest_for_preference(conn, preference_id)
    if latest is None:
        return now  # first digest is due immediately
    return latest.period_end + interval


def is_digest_due(conn: sqlite3.Connection, preference_id: str, preference_version: NotificationPreferenceVersion, now: datetime) -> bool:
    due_at = next_digest_time(conn, preference_id, preference_version, now)
    return due_at is not None and due_at <= now


def next_delivery_time(conn: sqlite3.Connection, delivery_id: str) -> datetime | None:
    delivery = service.get_delivery(conn, delivery_id)
    return delivery.next_attempt_at if delivery else None


def task_scheduler_command_examples() -> dict[str, str]:
    """"Generate task scheduler command examples" (the mission's own CLI
    requirement) — plain strings a user copies into their own scheduler, never
    executed by this codebase itself. `notification_cli.py`, like every other
    CLI in this project, always opens `src.core.config.DB_PATH` — there is no
    `--db-path` override flag.
    """
    deliver_cmd = "python -m src.ui.notification_cli deliver-pending"
    digest_cmd = "python -m src.ui.notification_cli generate-digest --frequency daily"
    return {
        "cron_deliver": f"*/5 * * * * cd /path/to/project && {deliver_cmd}",
        "cron_digest": f"0 8 * * * cd /path/to/project && {digest_cmd}",
        "windows_task_scheduler": f'schtasks /create /tn "NotificationDelivery" /tr "{deliver_cmd}" /sc minute /mo 5',
        "manual_cli": deliver_cmd,
    }
