"""App-wide configuration: paths every module needs, and .env loading.

This is deliberately not a revival of the old src/models/configuration.py (project_name,
search criteria, preferences, etc.) — that was a single fixed search configuration, which
is now the job of a database-backed SearchRequest (see docs/04_Search_Request.md), not
static app config. This module only holds things that are the same for every run of the
program: where files live, and process-wide settings loaded from the environment.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[2]

load_dotenv(PROJECT_ROOT / ".env")

# Overridable so a deployment can point these at a mounted persistent volume
# (e.g. a container filesystem where only /data survives a redeploy) instead
# of a path under the application code itself. Unset in local development —
# defaults are unchanged.
DATA_DIR = Path(os.environ.get("RENTAL_AGENT_DATA_DIR") or PROJECT_ROOT / "data")
OUTPUT_DIR = Path(os.environ.get("RENTAL_AGENT_OUTPUT_DIR") or PROJECT_ROOT / "output")
DB_PATH = DATA_DIR / "rental_intelligence.db"
