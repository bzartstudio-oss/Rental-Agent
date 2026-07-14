"""App-wide configuration: paths every module needs, and .env loading.

This is deliberately not a revival of the old src/models/configuration.py (project_name,
search criteria, preferences, etc.) — that was a single fixed search configuration, which
is now the job of a database-backed SearchRequest (see docs/04_Search_Request.md), not
static app config. This module only holds things that are the same for every run of the
program: where files live, and process-wide settings loaded from the environment.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "rental_intelligence.db"
OUTPUT_DIR = PROJECT_ROOT / "output"

load_dotenv(PROJECT_ROOT / ".env")
