"""Full + change-only HTML/JSON Monitoring Reports. See
docs/30_Continuous_Monitoring.md "Reporting". Mirrors
`discovery/automatic/report.py`'s own "plain string templating, reads from
already-stored data" shape.

"Change-only" is exactly the full report with the four run-lifecycle event
types (`MONITORING_RUN_*`/`REPORT_GENERATED`) filtered out — everything else
already *is* a detected change, so no second computation is needed.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from src.core.config import OUTPUT_DIR
from src.monitoring import service
from src.monitoring.models import MonitoringEventType, MonitoringReport, MonitoringRun, SavedSearch, SavedSearchVersion
from src.storage import apartment_repository

_LIFECYCLE_EVENT_TYPES = frozenset({
    MonitoringEventType.MONITORING_RUN_COMPLETED, MonitoringEventType.MONITORING_RUN_PARTIAL,
    MonitoringEventType.MONITORING_RUN_FAILED, MonitoringEventType.REPORT_GENERATED,
})


def generate_reports(
    conn: sqlite3.Connection, run: MonitoringRun, saved_search: SavedSearch, version: SavedSearchVersion,
    output_dir: Path = OUTPUT_DIR,
) -> MonitoringReport:
    events = service.get_events_for_run(conn, run.monitoring_run_id)
    change_events = [e for e in events if e.event_type not in _LIFECYCLE_EVENT_TYPES]

    full_data = _build_report_data(conn, run, saved_search, version, events)
    changes_data = _build_report_data(conn, run, saved_search, version, change_events)

    output_dir.mkdir(parents=True, exist_ok=True)
    full_json_path = output_dir / f"{run.monitoring_run_id}_monitoring_full.json"
    full_html_path = output_dir / f"{run.monitoring_run_id}_monitoring_full.html"
    changes_json_path = output_dir / f"{run.monitoring_run_id}_monitoring_changes.json"
    changes_html_path = output_dir / f"{run.monitoring_run_id}_monitoring_changes.html"

    full_json_path.write_text(json.dumps(full_data, indent=2, default=str), encoding="utf-8")
    full_html_path.write_text(_render_html(full_data, "Full Monitoring Report"), encoding="utf-8")
    changes_json_path.write_text(json.dumps(changes_data, indent=2, default=str), encoding="utf-8")
    changes_html_path.write_text(_render_html(changes_data, "Change-Only Monitoring Report"), encoding="utf-8")

    now = datetime.now(timezone.utc)
    for report_type, path in (
        ("full_html", full_html_path), ("full_json", full_json_path),
        ("changes_html", changes_html_path), ("changes_json", changes_json_path),
    ):
        service.record_report_artifact(conn, run.monitoring_run_id, report_type, str(path), now)

    return MonitoringReport(
        monitoring_run_id=run.monitoring_run_id, full_html_path=str(full_html_path), full_json_path=str(full_json_path),
        changes_html_path=str(changes_html_path), changes_json_path=str(changes_json_path), generated_at=now,
    )


def _build_report_data(conn: sqlite3.Connection, run: MonitoringRun, saved_search: SavedSearch, version: SavedSearchVersion, events: list) -> dict:
    event_rows = [_event_row(conn, event) for event in events]
    return {
        "monitoring_run_id": run.monitoring_run_id,
        "saved_search_id": saved_search.saved_search_id,
        "saved_search_name": saved_search.name,
        "saved_search_version": version.version,
        "status": run.status.value,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "platforms_attempted": run.platforms_attempted,
        "platforms_succeeded": run.platforms_succeeded,
        "platforms_failed": run.platforms_failed,
        "notes": run.notes,
        "events": event_rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _event_row(conn: sqlite3.Connection, event) -> dict:
    apartment = apartment_repository.get_apartment(conn, event.apartment_id) if event.apartment_id else None
    return {
        "event_id": event.event_id, "event_type": event.event_type, "severity": event.severity,
        "significance": event.significance, "explanation": event.explanation, "old_value": event.old_value,
        "new_value": event.new_value, "evidence": event.evidence, "detected_at": event.detected_at.isoformat(),
        "apartment_id": event.apartment_id, "platform_id": event.platform_id,
        "apartment_title": apartment.title if apartment else None,
        "apartment_url": apartment.url if apartment else None,
        "apartment_images": [img.local_path for img in apartment_repository.get_images(conn, event.apartment_id)] if apartment else [],
        "acknowledged": event.acknowledged,
    }


def _render_html(data: dict, title: str) -> str:
    rows = "".join(
        f"""<div class="event severity-{escape(e['severity'])}">
  <h3>{escape(e['event_type'])} <span class="severity">{escape(e['severity'])}</span></h3>
  <div class="facts">{escape(e['explanation'])}</div>
  {f'<div class="facts">Apartment: <a href="{escape(e["apartment_url"])}" target="_blank" rel="noopener">{escape(e["apartment_title"] or e["apartment_id"])}</a></div>' if e['apartment_url'] else ''}
  <div class="facts">Significance: {e['significance']:.2f} &nbsp;|&nbsp; Detected: {escape(e['detected_at'])}</div>
  {f'<div class="facts">Old -&gt; New: {escape(json.dumps(e["old_value"]))} -&gt; {escape(json.dumps(e["new_value"]))}</div>' if e['old_value'] or e['new_value'] else ''}
</div>"""
        for e in data["events"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(title)} — {escape(data['saved_search_name'])}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  .meta {{ color: #555; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .event {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 0.75rem; }}
  .event h3 {{ margin: 0 0 0.25rem; font-size: 1rem; }}
  .severity {{ display: inline-block; border-radius: 4px; padding: 0.1rem 0.5rem; font-size: 0.8rem; color: #fff; background: #666; }}
  .severity-critical .severity {{ background: #a13c3c; }}
  .severity-warning .severity {{ background: #a15c00; }}
  .severity-info .severity {{ background: #2a6f2a; }}
  .facts {{ color: #444; font-size: 0.85rem; margin: 0.2rem 0; }}
</style>
</head>
<body>
<h1>{escape(title)}</h1>
<div class="meta">
  Saved Search: {escape(data['saved_search_name'])} (version {data['saved_search_version']})<br>
  Monitoring Run: {escape(data['monitoring_run_id'])}<br>
  Status: {escape(data['status'])}<br>
  Platforms attempted: {escape(", ".join(data['platforms_attempted']) or 'n/a')}<br>
  Platforms failed: {escape(", ".join(data['platforms_failed']) or 'none')}<br>
  Generated: {escape(data['generated_at'])}
</div>
{rows or '<p>No events.</p>'}
</body>
</html>
"""
