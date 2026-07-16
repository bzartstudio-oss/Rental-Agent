"""Shared fixture builders for `tests/web/` (not a test module — no `test_`
prefix). Mirrors `tests/notifications/helpers.py`'s own shape.
"""

from __future__ import annotations

import re
import tempfile
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
from tests.support import isolated_collectors

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


@contextmanager
def web_test_app() -> Iterator[tuple[Flask, Database, Path]]:
    """A real Flask app, a real temp SQLite database, and a demo platform
    already registered — everything `test_client()`-driven tests need,
    without touching real project `data/`/`output/`.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db = Database(db_path=tmp_path / "test.db")
        with db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform", name="Demo Platform (reference/demo connector)", country="N/A (local fixture)",
                    homepage="local-fixture", connector_available=True, connector_name="demo_platform",
                    created_at=datetime.now(timezone.utc),
                ),
            )
        configuration = WebConfiguration(host="127.0.0.1", port=0, secret_key="test-secret", data_dir=tmp_path, output_dir=tmp_path / "output")
        with isolated_collectors(tmp_path):
            app = create_app(db=db, configuration=configuration)
            app.config["TESTING"] = True
            app.config["PROPAGATE_EXCEPTIONS"] = True
            yield app, db, tmp_path


def csrf_token_from(html: str) -> str:
    match = CSRF_RE.search(html)
    assert match is not None, "no CSRF token found in rendered page"
    return match.group(1)
