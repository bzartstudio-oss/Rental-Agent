"""Monthly API call budget for RentCast — v2.7 Milestone 2.7.2 (RentCast
Resilience). See docs/46_Version_2.7_Planning.md Milestone 2.7.2: RentCast's
free tier is 50 requests/month and nothing previously stopped one broad
search from silently exhausting it. `try_consume_call()` is the single
atomic operation that makes "concurrent requests cannot exceed the budget"
true on SQLite without a separate locking mechanism — the same "one atomic
conditional UPDATE" idiom `storage.monitoring_repository.claim_due_run()`
already established for cross-process/cross-thread claims (see
docs/30_Continuous_Monitoring.md).

Deliberately its own small module rather than a new `storage/*_repository.py`
— `provider_call_budget` has exactly one caller (`RentCastConnector`) and one
concern (count-and-gate), not a general read/write API other engines need.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


def _period_key(now: datetime) -> str:
    """UTC "YYYY-MM" — the natural month boundary a budget resets on. Callers
    must pass a UTC `now` (every other timestamp in this codebase already is).
    """
    return now.strftime("%Y-%m")


def try_consume_call(conn: sqlite3.Connection, provider_id: str, monthly_limit: int, now: datetime) -> bool:
    """Attempts to reserve one call against `provider_id`'s budget for the
    calendar month `now` falls in. Returns whether *this* call was granted.

    Two statements, but atomic in effect: both run inside the same connection
    inside one caller-managed transaction (`Database.transaction()`), so
    SQLite's single-writer file lock serializes any concurrent caller the same
    way `claim_due_run()`'s single `UPDATE` does — no second connection can
    interleave between the `INSERT OR IGNORE` and the conditional `UPDATE`
    below, so two callers racing for the last unit of budget can never both
    win.
    """
    period_key = _period_key(now)
    now_iso = now.isoformat()

    conn.execute(
        """
        INSERT OR IGNORE INTO provider_call_budget
            (provider_id, period_key, call_count, monthly_limit, created_at, updated_at)
        VALUES (?, ?, 0, ?, ?, ?)
        """,
        (provider_id, period_key, monthly_limit, now_iso, now_iso),
    )

    cursor = conn.execute(
        """
        UPDATE provider_call_budget SET call_count = call_count + 1, updated_at = ?
        WHERE provider_id = ? AND period_key = ? AND call_count < monthly_limit
        """,
        (now_iso, provider_id, period_key),
    )
    return cursor.rowcount > 0


def current_usage(conn: sqlite3.Connection, provider_id: str, now: datetime) -> tuple[int, int]:
    """`(call_count, monthly_limit)` for the calendar month `now` falls in, or
    `(0, 0)` if nothing has been recorded for this provider yet this period —
    read-only, never creates a row (unlike `try_consume_call`).
    """
    period_key = _period_key(now)
    row = conn.execute(
        "SELECT call_count, monthly_limit FROM provider_call_budget WHERE provider_id = ? AND period_key = ?",
        (provider_id, period_key),
    ).fetchone()
    if row is None:
        return 0, 0
    return row["call_count"], row["monthly_limit"]
