"""The scheduling interface. See docs/30_Continuous_Monitoring.md "Scheduling
Interface" — every mission-named function lives here: `due_saved_searches()`,
`next_run_time()`, `mark_run_started()`, `mark_run_completed()`,
`mark_run_failed()`, `claim_due_run()`, `release_run_claim()`.

"Do not create a background daemon tied to one operating system. Create
scheduling interfaces that can later be driven by: Windows Task Scheduler,
cron, a future worker service, a future web application, manual CLI
execution" (the mission's own words) — nothing here loops or sleeps; every
function is a single, idempotent database operation a caller invokes once,
from whatever triggers it (a cron line, a Task Scheduler action, or a person
typing a CLI command).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.monitoring import service
from src.monitoring.models import MonitoringConfiguration, MonitoringHealth, MonitoringPolicy, MonitoringRunStatus, MonitoringSchedule, SavedSearch

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def due_saved_searches(conn, now: datetime) -> list[SavedSearch]:
    """Every enabled saved search whose schedule is due and not currently
    claimed by another worker — "enabled saved searches and next run time"
    (the mission's own index).
    """
    schedules = service.get_due_schedules(conn, now)
    saved_searches = []
    for schedule in schedules:
        saved_search = service.get_saved_search(conn, schedule.saved_search_id)
        if saved_search is not None:
            saved_searches.append(saved_search)
    return saved_searches


def next_run_time(conn, saved_search_id: str) -> datetime | None:
    schedule = service.get_schedule(conn, saved_search_id)
    return schedule.next_run_at if schedule is not None else None


def compute_next_run_at(policy: MonitoringPolicy, now: datetime) -> datetime | None:
    """`None` means "manual trigger only" — no policy field implies automatic
    scheduling by accident.
    """
    if policy.manual_only:
        return None
    if policy.interval_minutes:
        return now + timedelta(minutes=policy.interval_minutes)
    if policy.daily_at:
        hour, minute = (int(part) for part in policy.daily_at.split(":"))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    if policy.weekly_on:
        day_name, time_part = policy.weekly_on.split(":", 1)
        hour, minute = (int(part) for part in time_part.split(":"))
        target_weekday = _WEEKDAYS.index(day_name.strip().lower())
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (target_weekday - now.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate
    return None


def claim_due_run(conn, saved_search_id: str, claimed_by: str, now: datetime, ttl_minutes: float) -> bool:
    """Atomically claims a due run — see
    `storage.monitoring_repository.claim_due_run()` for the actual locking
    mechanism ("Prevent two workers from executing the same scheduled run
    simultaneously," the mission's own words).
    """
    expires_at = now + timedelta(minutes=ttl_minutes)
    return service.claim_due_run(conn, saved_search_id, claimed_by, now, expires_at)


def release_run_claim(conn, saved_search_id: str) -> None:
    service.release_run_claim(conn, saved_search_id)


def mark_run_started(conn, saved_search_id: str, now: datetime) -> None:
    schedule = service.get_schedule(conn, saved_search_id) or MonitoringSchedule(saved_search_id=saved_search_id)
    schedule.last_run_at = now
    schedule.last_run_status = "running"
    service.update_schedule(conn, schedule)


def mark_run_completed(conn, saved_search_id: str, now: datetime, policy: MonitoringPolicy) -> None:
    _finalize(conn, saved_search_id, now, policy, status="completed")


def mark_run_partial(conn, saved_search_id: str, now: datetime, policy: MonitoringPolicy) -> None:
    _finalize(conn, saved_search_id, now, policy, status="partial")


def mark_run_failed(conn, saved_search_id: str, now: datetime, policy: MonitoringPolicy) -> None:
    _finalize(conn, saved_search_id, now, policy, status="failed")


def _finalize(conn, saved_search_id: str, now: datetime, policy: MonitoringPolicy, *, status: str) -> None:
    schedule = service.get_schedule(conn, saved_search_id) or MonitoringSchedule(saved_search_id=saved_search_id)
    schedule.last_run_at = now
    schedule.last_run_status = status
    schedule.next_run_at = compute_next_run_at(policy, now)
    service.update_schedule(conn, schedule)
    release_run_claim(conn, saved_search_id)


def compute_health(conn, saved_search_id: str) -> MonitoringHealth:
    saved_search = service.get_saved_search(conn, saved_search_id)
    if saved_search is None:
        raise ValueError(f"No such saved search {saved_search_id!r}")
    schedule = service.get_schedule(conn, saved_search_id)
    runs = sorted(service.get_runs_for_saved_search(conn, saved_search_id), key=lambda r: r.started_at, reverse=True)

    consecutive_failures = 0
    for run in runs:
        if run.status is MonitoringRunStatus.FAILED:
            consecutive_failures += 1
        else:
            break

    now = datetime.now(runs[0].started_at.tzinfo) if runs else None
    is_claimed = bool(
        schedule is not None and schedule.claimed_by is not None
        and (schedule.claim_expires_at is None or now is None or schedule.claim_expires_at >= now)
    )

    return MonitoringHealth(
        saved_search_id=saved_search_id, enabled=saved_search.enabled,
        last_run_status=schedule.last_run_status if schedule else None,
        last_run_at=schedule.last_run_at if schedule else None,
        next_run_at=schedule.next_run_at if schedule else None,
        is_claimed=is_claimed, claim_expires_at=schedule.claim_expires_at if schedule else None,
        consecutive_failure_count=consecutive_failures,
    )


def task_scheduler_command_examples(saved_search_id: str, db_path: str) -> dict[str, str]:
    """"Generate task scheduler command examples" (the mission's own CLI
    requirement) — plain strings a user copies into their own scheduler, never
    executed by this codebase itself. `db_path` is shown as a comment, not a
    real flag: `monitoring_cli.py` (like every other CLI in this project)
    always opens `src.core.config.DB_PATH` — there is no `--db-path` override
    to pass, so the example doesn't invent one.
    """
    python_cmd = f"python -m src.ui.monitoring_cli run-now --saved-search-id {saved_search_id}"  # uses {db_path}
    return {
        "cron": f"*/15 * * * * cd /path/to/project && {python_cmd}",
        "windows_task_scheduler": (
            f'schtasks /create /tn "Monitor {saved_search_id}" /tr "{python_cmd}" '
            f'/sc minute /mo 15'
        ),
        "manual_cli": python_cmd,
    }
