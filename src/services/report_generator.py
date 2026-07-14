"""HTML Report Generator — see docs/09_Report_System.md.

Reads from the database (search_results, not in-memory ranking output) so a report can be
regenerated later from stored data alone — consistent with Principle 4 (reproducible,
comparable over time). Uses plain string templating rather than Jinja2: Jinja2 isn't an
installed project dependency, and V1's report layout is simple enough not to need a
templating engine — see docs/09_Report_System.md, resolving its "proposal, not yet locked
in" note.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from src.core.config import OUTPUT_DIR
from src.storage import apartment_repository, search_repository
from src.storage.database import Database


def generate_report(db: Database, search_id: str, output_dir: Path = OUTPUT_DIR) -> Path:
    with db.transaction() as conn:
        search = search_repository.get_search_request(conn, search_id)
        results = search_repository.get_search_results(conn, search_id)

        rows_html = []
        for result in results:
            apartment = apartment_repository.get_apartment(conn, result.apartment_id)
            images = apartment_repository.get_images(conn, result.apartment_id)
            price_history = apartment_repository.get_price_history(conn, result.apartment_id)
            availability_history = apartment_repository.get_availability_history(conn, result.apartment_id)
            rows_html.append(_render_result(result, apartment, images, price_history, availability_history))

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{search_id}.html"
    report_path.write_text(_render_page(search, rows_html), encoding="utf-8")
    return report_path


def _render_page(search, rows_html: list[str]) -> str:
    criteria = json.loads(search.criteria_json) if search else {}
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Rental Search Report — {escape(search.id if search else '')}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  .meta {{ color: #555; font-size: 0.9rem; margin-bottom: 2rem; }}
  .listing {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
  .listing h2 {{ margin: 0 0 0.25rem; font-size: 1.1rem; }}
  .rank {{ display: inline-block; background: #222; color: #fff; border-radius: 4px; padding: 0.1rem 0.5rem; font-size: 0.85rem; margin-right: 0.5rem; }}
  .price {{ font-weight: bold; }}
  .facts {{ color: #444; font-size: 0.9rem; margin: 0.25rem 0; }}
  .score-breakdown {{ font-size: 0.8rem; color: #666; }}
  .photos img {{ height: 80px; margin: 0.25rem 0.25rem 0 0; border-radius: 4px; }}
  .history {{ font-size: 0.8rem; color: #666; margin-top: 0.5rem; }}
  a {{ color: #0055aa; }}
</style>
</head>
<body>
<h1>Rental Search Report</h1>
<div class="meta">
  Search ID: {escape(search.id if search else '')}<br>
  Location: {escape(criteria.get('location', ''))}<br>
  Criteria: {escape(json.dumps(criteria.get('criteria', {})))}<br>
  Generated: {escape(datetime.now(timezone.utc).isoformat())}
</div>
{''.join(rows_html) if rows_html else '<p>No matching listings.</p>'}
</body>
</html>
"""


def _render_result(result, apartment, images, price_history, availability_history) -> str:
    photos_html = "".join(
        f'<img src="{escape(Path(image.local_path).as_uri())}" alt="listing photo">' for image in images
    )
    breakdown_html = ", ".join(f"{escape(k)}: {v:.2f}" for k, v in json.loads(result.score_breakdown_json).items())
    price_trend = " → ".join(f"{entry.price:.0f}" for entry in price_history)
    status_trend = " → ".join(escape(entry.status) for entry in availability_history)

    return f"""<div class="listing">
  <span class="rank">#{result.rank}</span>
  <h2>{escape(apartment.title)}</h2>
  <div class="price">${result.price_at_search:.0f}/mo — {escape(result.status_at_search)}</div>
  <div class="facts">{apartment.bedrooms or '?'} bed · {apartment.bathrooms or '?'} bath · {apartment.sqft or '?'} sqft · {escape(apartment.address_raw or '')}</div>
  <div class="facts">Score: {result.score:.2f} <span class="score-breakdown">({breakdown_html})</span></div>
  <div class="photos">{photos_html}</div>
  <div class="history">Price history: {price_trend or 'n/a'} &nbsp;|&nbsp; Availability history: {status_trend or 'n/a'}</div>
  <div><a href="{escape(apartment.url)}" target="_blank" rel="noopener">Original listing</a></div>
</div>
"""
