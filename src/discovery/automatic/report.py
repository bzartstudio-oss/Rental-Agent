"""HTML + JSON Discovery Report generator — the mission's own REPORTING section:
request, providers used, candidates found, verified/unsupported platforms,
connector availability, confidence, evidence summary, classifications,
duplicates, warnings, manual-review queue, geographic/rental-category
coverage, original URLs. Mirrors `services/report_generator.py`'s own "plain
string templating, no Jinja2" shape (not an installed dependency) and reads
from already-stored data via `service.py`, the same "reproducible from stored
data alone" principle.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from src.core.config import OUTPUT_DIR
from src.discovery.automatic import service
from src.discovery.automatic.models import PlatformCandidate, PlatformDiscoveryResult


def generate_report(
    conn: sqlite3.Connection, result: PlatformDiscoveryResult, output_dir: Path = OUTPUT_DIR,
) -> tuple[Path, Path]:
    """Writes `<run_id>_discovery.json` and `<run_id>_discovery.html` into
    `output_dir`. Returns `(json_path, html_path)`.
    """
    data = _build_report_data(conn, result)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{result.run.run_id}_discovery.json"
    html_path = output_dir / f"{result.run.run_id}_discovery.html"

    json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    html_path.write_text(_render_html(data), encoding="utf-8")
    return json_path, html_path


def _build_report_data(conn: sqlite3.Connection, result: PlatformDiscoveryResult) -> dict:
    all_candidates = result.supported + result.unsupported + result.needs_review + result.duplicates

    return {
        "run_id": result.run.run_id,
        "request": result.run.request.as_dict(),
        "started_at": result.run.started_at.isoformat(),
        "completed_at": result.run.completed_at.isoformat() if result.run.completed_at else None,
        "providers_used": result.run.providers_used,
        "warnings": result.warnings,
        "totals": {
            "total_candidates": result.run.total_candidates,
            "new_candidates": result.run.new_candidate_count,
            "duplicates": result.run.duplicate_count,
            "verified": result.run.verified_count,
            "supported": result.run.supported_count,
            "unsupported": result.run.unsupported_count,
        },
        "supported_platforms": [_candidate_summary(conn, c) for c in result.supported],
        "unsupported_platforms": [_candidate_summary(conn, c) for c in result.unsupported],
        "manual_review_queue": [_candidate_summary(conn, c) for c in result.needs_review],
        "duplicates": [_candidate_summary(conn, c) for c in result.duplicates],
        "geographic_coverage": sorted({c.city for c in all_candidates if c.city}),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _candidate_summary(conn: sqlite3.Connection, candidate: PlatformCandidate) -> dict:
    evidence = service.get_evidence_for_candidate(conn, candidate.candidate_id)
    evidence_type_counts: dict[str, int] = {}
    for item in evidence:
        evidence_type_counts[item.evidence_type] = evidence_type_counts.get(item.evidence_type, 0) + 1

    capabilities = service.get_capability_estimates(conn, candidate.candidate_id)
    verification = service.get_verification_results(conn, candidate.candidate_id)

    return {
        "candidate_id": candidate.candidate_id,
        "name": candidate.name,
        "original_url": candidate.raw_url,
        "normalized_domain": candidate.normalized_domain,
        "status": candidate.status.value,
        "classification": candidate.classification.value,
        "confidence": candidate.confidence,
        "matched_platform_id": candidate.matched_platform_id,
        "country": candidate.country, "region": candidate.region, "city": candidate.city,
        "evidence_summary": evidence_type_counts,
        "verification": [{"check_type": v.check_type, "result": v.result} for v in verification],
        "capability_estimates": {c.capability_key: c.estimated_value for c in capabilities},
    }


def _render_html(data: dict) -> str:
    def section(title: str, candidates: list[dict]) -> str:
        if not candidates:
            return f"<h2>{escape(title)}</h2><p>None.</p>"
        rows = "".join(
            f"""<div class="candidate">
  <h3>{escape(c['name'])} <span class="status">{escape(c['status'])}</span></h3>
  <div class="facts">URL: <a href="{escape(c['original_url'])}" target="_blank" rel="noopener">{escape(c['original_url'])}</a></div>
  <div class="facts">Classification: {escape(c['classification'])} &nbsp;|&nbsp; Confidence: {c['confidence']}</div>
  <div class="facts">Location: {escape(c['country'] or 'n/a')} / {escape(c['region'] or 'n/a')} / {escape(c['city'] or 'n/a')}</div>
  <div class="facts">Evidence: {escape(json.dumps(c['evidence_summary']))}</div>
  <div class="facts">Capabilities (estimated): {escape(json.dumps(c['capability_estimates']))}</div>
</div>"""
            for c in candidates
        )
        return f"<h2>{escape(title)}</h2>{rows}"

    warnings_html = "".join(f"<li>{escape(w)}</li>" for w in data["warnings"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Platform Discovery Report — {escape(data['run_id'])}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  .meta {{ color: #555; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .candidate {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 0.75rem; }}
  .candidate h3 {{ margin: 0 0 0.25rem; font-size: 1rem; }}
  .status {{ display: inline-block; background: #222; color: #fff; border-radius: 4px; padding: 0.1rem 0.5rem; font-size: 0.8rem; }}
  .facts {{ color: #444; font-size: 0.85rem; margin: 0.2rem 0; }}
  .warnings {{ color: #a15c00; }}
</style>
</head>
<body>
<h1>Platform Discovery Report</h1>
<div class="meta">
  Run ID: {escape(data['run_id'])}<br>
  Request: {escape(json.dumps(data['request']))}<br>
  Providers used: {escape(", ".join(data['providers_used']))}<br>
  Totals: {escape(json.dumps(data['totals']))}<br>
  Geographic coverage: {escape(", ".join(data['geographic_coverage']) or 'n/a')}<br>
  Generated: {escape(data['generated_at'])}
</div>
{f'<ul class="warnings">{warnings_html}</ul>' if warnings_html else ''}
{section('Supported Platforms (connector available)', data['supported_platforms'])}
{section('Unsupported Platforms', data['unsupported_platforms'])}
{section('Manual Review Queue', data['manual_review_queue'])}
{section('Duplicates', data['duplicates'])}
</body>
</html>
"""
