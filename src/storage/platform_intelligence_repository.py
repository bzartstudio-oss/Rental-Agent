"""Persistence for `platform_performance_observations` — the Knowledge Engine's raw,
append-only memory (schema added in migration 0001, Sprint V2.0.1; real read/write
logic added in v2.0 Step 4). See docs/16_Knowledge_Engine.md for what each metric means
and how it's computed. Same convention as every other repository module: pure data
access, no decisions about *when*/*what* to write — that's src/knowledge/knowledge_service.py
and core/agent.py's job (docs/01_System_Architecture.md).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.storage.models import PlatformPerformanceObservation, iso, parse_iso


def add_observation(conn: sqlite3.Connection, observation: PlatformPerformanceObservation) -> int:
    cursor = conn.execute(
        """
        INSERT INTO platform_performance_observations (
            platform_id, search_id, results_count, failed, response_time_ms,
            extraction_quality_score, image_quality_score, availability_quality_score,
            duplicate_rate, ranking_usefulness_score, parsing_success, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation.platform_id,
            observation.search_id,
            observation.results_count,
            int(observation.failed),
            observation.response_time_ms,
            observation.extraction_quality_score,
            observation.image_quality_score,
            observation.availability_quality_score,
            observation.duplicate_rate,
            observation.ranking_usefulness_score,
            int(observation.parsing_success),
            iso(observation.observed_at),
        ),
    )
    return cursor.lastrowid


def get_recent_observations(
    conn: sqlite3.Connection, platform_id: str, limit: int = 20
) -> list[PlatformPerformanceObservation]:
    """Newest-first, capped at `limit` — the "recent window" docs/16_Knowledge_Engine.md
    rollups are computed over (the last 20 observations for a platform, or all of them
    if fewer exist), so reliability reflects *current* behavior rather than an all-time
    average a platform can never recover from after one bad month.
    """
    rows = conn.execute(
        "SELECT * FROM platform_performance_observations WHERE platform_id = ? "
        "ORDER BY observed_at DESC LIMIT ?",
        (platform_id, limit),
    ).fetchall()
    return [_row_to_observation(row) for row in rows]


def get_all_observations(conn: sqlite3.Connection, platform_id: str) -> list[PlatformPerformanceObservation]:
    rows = conn.execute(
        "SELECT * FROM platform_performance_observations WHERE platform_id = ? ORDER BY observed_at",
        (platform_id,),
    ).fetchall()
    return [_row_to_observation(row) for row in rows]


def get_last_observed_at(conn: sqlite3.Connection, platform_id: str, failed: bool) -> datetime | None:
    """`get_last_observed_at(..., failed=False)` is "Last Successful Search";
    `failed=True` is "Last Failed Search" — both from the v2.0 Step 4 mission's
    PLATFORMS tracking list.
    """
    row = conn.execute(
        "SELECT MAX(observed_at) AS last_observed FROM platform_performance_observations "
        "WHERE platform_id = ? AND failed = ?",
        (platform_id, int(failed)),
    ).fetchone()
    return parse_iso(row["last_observed"]) if row and row["last_observed"] else None


def count_all_observations(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS total FROM platform_performance_observations").fetchone()
    return row["total"] if row else 0


def _row_to_observation(row: sqlite3.Row) -> PlatformPerformanceObservation:
    return PlatformPerformanceObservation(
        id=row["id"],
        platform_id=row["platform_id"],
        search_id=row["search_id"],
        results_count=row["results_count"],
        failed=bool(row["failed"]),
        response_time_ms=row["response_time_ms"],
        extraction_quality_score=row["extraction_quality_score"],
        image_quality_score=row["image_quality_score"],
        availability_quality_score=row["availability_quality_score"],
        duplicate_rate=row["duplicate_rate"],
        ranking_usefulness_score=row["ranking_usefulness_score"],
        parsing_success=bool(row["parsing_success"]),
        observed_at=parse_iso(row["observed_at"]),
    )
