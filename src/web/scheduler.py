"""`MonitoringScheduler` — in-process scheduled monitoring. v2.7 Milestone
2.7.3 (docs/46_Version_2.7_Planning.md). Answers part of the open question
`notes/Questions.md` already logged for `MonitoringConfiguration`'s
production defaults ("what should drive this once it runs somewhere other
than a manually-triggered CLI") for the web deployment specifically: a
background daemon thread inside the *same* process and against the *same*
SQLite file the web app already uses — no Redis, Celery, external cron, or
second Render service, and no way for it to see a different database than
whatever request handlers are reading/writing.

Adds no monitoring business logic of its own. Every tick calls
`MonitoringEngine.run_due()` exactly as published (v2.5 Step 14) — the same
atomic `claim_due_run()` that already makes "two workers can't execute the
same scheduled run simultaneously" true is what also makes this scheduler
safe to run alongside a manual "Run Now" click or a real second process
(e.g. the CLI) without any new locking of its own.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from src.monitoring.engine import MonitoringEngine
from src.storage.database import Database
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_INTERVAL_SECONDS = 60.0
WORKER_ID = "web-scheduler"


class MonitoringScheduler:
    """One instance per `create_app()` call, stored on `app.extensions` —
    not a module-level global, so multiple apps (e.g. one per test) each get
    their own independent scheduler against their own database, while a real
    production process (which only ever calls `create_app()` once, at
    `src/web/wsgi.py` import time) still gets exactly one scheduler thread.

    `start()`/`stop()` are both idempotent and thread-safe: a second
    concurrent `start()` while already running is a no-op, matching this
    codebase's other "one atomic guard, no separate locking mechanism"
    precedent (`monitoring_schedules`' own claim column).
    """

    def __init__(
        self,
        db: Database,
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        engine: MonitoringEngine | None = None,
        worker_id: str = WORKER_ID,
    ) -> None:
        self._db = db
        self._interval_seconds = interval_seconds
        self._engine = engine or MonitoringEngine()
        self._worker_id = worker_id
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.run_count = 0  # ticks attempted (success or failure) — introspectable for tests, not used for control flow

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> bool:
        """Starts the background thread. Returns `True` if this call actually
        started it, `False` if a thread was already running (idempotent —
        never raises, never starts a second thread).
        """
        with self._lock:
            if self.is_running:
                logger.info("monitoring scheduler start requested but already running")
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="monitoring-scheduler", daemon=True)
            self._thread.start()
            logger.info("monitoring scheduler started", extra={"interval_seconds": self._interval_seconds, "worker_id": self._worker_id})
            return True

    def stop(self, *, timeout: float = 5.0) -> None:
        """Signals the loop to exit and waits up to `timeout` seconds for it
        to finish its current tick. Safe to call even if never started, or
        more than once — never raises.
        """
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()
        thread.join(timeout=timeout)
        with self._lock:
            self._thread = None
        logger.info("monitoring scheduler stopped")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(self._interval_seconds)

    def _tick(self) -> None:
        """One scheduling cycle: reuses `MonitoringEngine.run_due()` exactly
        as every other caller does. Any exception — a broken connector, a
        database hiccup, anything — is caught here so a single bad cycle
        never kills the background thread (and, since this thread is never
        on the request path, never the web server either); the next tick
        simply tries again. Never logs exception details beyond the message
        (never a raw traceback with request/credential data, matching every
        other `except Exception as exc: ... str(exc)` in this codebase).
        """
        try:
            runs = self._engine.run_due(self._db, worker_id=self._worker_id, now=datetime.now(timezone.utc))
            if runs:
                logger.info("scheduled monitoring executed", extra={"run_count": len(runs)})
        except Exception as exc:  # noqa: BLE001 — a failed cycle must never stop future cycles or crash the process
            logger.warning("scheduled monitoring cycle failed, will retry next interval", extra={"error": str(exc)})
        finally:
            self.run_count += 1  # ticks attempted, success or failure — proves the loop kept going
