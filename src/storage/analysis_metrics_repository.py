"""Persistence for `apartment_analysis_metrics` — the Deep Analysis Engine's output
store (schema added in migration 0001, extended in migration 0003, real read/write
logic added in v2.0 Step 6). See docs/19_Analysis_Engine.md for the analyzer framework
that decides *what* to compute; this module is pure data access, same convention as
every other repository — no decisions about *when*/*what* to write.

`evidence_json` stores `{"evidence": [...], "warnings": [...]}` — one column instead of
two, since both are just lists of human-readable strings attached to the same metric
row and neither needs independent querying.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from src.storage.models import ApartmentAnalysisMetric, iso, parse_iso


def add_metric(conn: sqlite3.Connection, metric: ApartmentAnalysisMetric) -> int:
    cursor = conn.execute(
        """
        INSERT INTO apartment_analysis_metrics (
            apartment_id, metric_name, metric_value, metric_unit, source_module,
            search_id, computed_at, confidence, evidence_json, analyzer_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metric.apartment_id,
            metric.metric_name,
            metric.metric_value,
            metric.metric_unit,
            metric.source_module,
            metric.search_id,
            iso(metric.computed_at),
            metric.confidence,
            json.dumps({"evidence": metric.evidence or [], "warnings": metric.warnings or []}),
            metric.analyzer_version,
        ),
    )
    return cursor.lastrowid


def get_metrics_for_apartment(
    conn: sqlite3.Connection, apartment_id: str, metric_name: str | None = None
) -> list[ApartmentAnalysisMetric]:
    """Every recorded metric for this apartment, oldest first — the full history. Pass
    `metric_name` to scope to just one metric's timeline (e.g. `"walking_distance"` or
    `"composite:location_score"`).
    """
    if metric_name is not None:
        rows = conn.execute(
            "SELECT * FROM apartment_analysis_metrics WHERE apartment_id = ? AND metric_name = ? "
            "ORDER BY computed_at",
            (apartment_id, metric_name),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM apartment_analysis_metrics WHERE apartment_id = ? ORDER BY computed_at",
            (apartment_id,),
        ).fetchall()
    return [_row_to_metric(row) for row in rows]


def get_latest_metrics_for_apartment(conn: sqlite3.Connection, apartment_id: str) -> list[ApartmentAnalysisMetric]:
    """The most recent analysis *run* for this apartment — every metric sharing the
    latest `computed_at` timestamp (a full run stamps every metric with the same
    instant, see `src/analysis/models.py::AnalysisContext`). Empty if this apartment
    has never had any metric successfully computed (no evidence yet, ever).
    """
    all_metrics = get_metrics_for_apartment(conn, apartment_id)
    if not all_metrics:
        return []
    latest_computed_at = max(metric.computed_at for metric in all_metrics)
    return [metric for metric in all_metrics if metric.computed_at == latest_computed_at]


def get_metrics_for_search(conn: sqlite3.Connection, search_id: str) -> list[ApartmentAnalysisMetric]:
    rows = conn.execute(
        "SELECT * FROM apartment_analysis_metrics WHERE search_id = ? ORDER BY apartment_id, metric_name",
        (search_id,),
    ).fetchall()
    return [_row_to_metric(row) for row in rows]


def _row_to_metric(row: sqlite3.Row) -> ApartmentAnalysisMetric:
    payload = json.loads(row["evidence_json"]) if row["evidence_json"] else {}
    return ApartmentAnalysisMetric(
        id=row["id"],
        apartment_id=row["apartment_id"],
        metric_name=row["metric_name"],
        metric_value=row["metric_value"],
        metric_unit=row["metric_unit"],
        source_module=row["source_module"],
        search_id=row["search_id"],
        computed_at=parse_iso(row["computed_at"]),
        confidence=row["confidence"],
        evidence=payload.get("evidence", []),
        warnings=payload.get("warnings", []),
        analyzer_version=row["analyzer_version"],
    )
