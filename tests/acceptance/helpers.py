"""Shared fixture builders for `tests/acceptance/` — see
docs/33_Release_Candidate_Acceptance.md. Not a test module itself (no
`test_` prefix). Mirrors `tests/web/helpers.py`'s own shape.
"""

from __future__ import annotations

import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from flask import Flask

from src.discovery import platform_registry
from src.storage.database import Database
from src.storage.models import Platform
from src.web.application import create_app
from src.web.configuration import WebConfiguration
from src.web.constants import TERMINAL_JOB_STATUSES
from tests.support import isolated_collectors

VALENCIA_ADDRESS = "Carrer Mestre Serrano, 3, 46120 Alboraia, Valencia, Spain"


@contextmanager
def acceptance_app() -> Iterator[tuple[Flask, Database, Path]]:
    """A real Flask app, a real temp SQLite database, and both demo
    platforms registered — what every user-journey acceptance test drives.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db = Database(db_path=tmp_path / "acceptance.db")
        with db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform", name="Demo Platform (reference/demo connector)", country="N/A (local fixture)",
                    homepage="local-fixture", connector_available=True, connector_name="demo_platform",
                    created_at=datetime.now(timezone.utc),
                ),
            )
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform_two", name="Demo Platform Two (reference/demo connector)", country="N/A (local fixture)",
                    homepage="local-fixture-2", connector_available=True, connector_name="demo_platform_two",
                    created_at=datetime.now(timezone.utc),
                ),
            )
        configuration = WebConfiguration(host="127.0.0.1", port=0, secret_key="acceptance-secret", data_dir=tmp_path, output_dir=tmp_path / "output")
        with isolated_collectors(tmp_path):
            app = create_app(db=db, configuration=configuration)
            app.config["TESTING"] = True
            yield app, db, tmp_path


def wait_for_job(client, job_url: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    job = None
    while time.monotonic() < deadline:
        resp = client.get(job_url, headers={"Accept": "application/json"})
        job = resp.get_json()["job"]
        if job["status"] in TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.3)
    raise TimeoutError(f"job at {job_url} never reached a terminal state: {job}")


def csrf_token_from(html: str) -> str:
    import re

    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None, "no CSRF token found in rendered page"
    return match.group(1)
