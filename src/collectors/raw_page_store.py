"""Persists raw fetch output (HTML) to data/raw_pages/ — the file half of the audit trail
described in docs/03_Data_Model.md (`raw_captures`) / docs/06_Connector_Framework.md.

Pure file I/O: no database writes here (that's storage/'s job) — this module hands back a
path, and whoever calls it (a connector) decides what to do with it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.core.config import DATA_DIR

RAW_PAGES_DIR = DATA_DIR / "raw_pages"


def save_page(platform_id: str, content: str, suffix: str = "html", base_dir: Path = RAW_PAGES_DIR) -> Path:
    """Save `content` under <base_dir>/<platform_id>/<timestamp>.<suffix>, returning the
    path written. One file per fetch, never overwritten — a capture from three searches
    ago is still there if something later needs to be traced back to what was actually
    on the page at the time (Principle 1: never lose information).

    `base_dir` defaults to the real data/raw_pages/ but is overridable so tests don't
    write into real project data.
    """
    platform_dir = base_dir / platform_id
    platform_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = platform_dir / f"{timestamp}.{suffix}"
    path.write_text(content, encoding="utf-8")
    return path
