"""HTML Report Generator — see docs/09_Report_System.md.

Reads from the database (search_results, not in-memory ranking output) so a report can be
regenerated later from stored data alone — consistent with Principle 4 (reproducible,
comparable over time). Uses plain string templating rather than Jinja2: Jinja2 isn't an
installed project dependency, and V1's report layout is simple enough not to need a
templating engine — see docs/09_Report_System.md, resolving its "proposal, not yet locked
in" note.

v2.0 Step 6 — `analysis_results` is an optional, in-memory-only parameter: the Deep
Analysis Engine deliberately doesn't persist a "no evidence" result (see
`src/analysis/analysis_service.py`), so a report generated in the same run that
computed it (the normal path, via `core/agent.py`) can show *why* an analyzer had
nothing to say, while a report regenerated later without fresh results (not currently
a real feature — `report_path` is written once per search) simply omits the section.
Every existing caller that doesn't pass this argument gets byte-identical behavior to
before this sprint.

Provider Abstraction Layer — `ai_summary` is another optional, in-memory-only
parameter, the same shape as `analysis_results`: an AI provider's summary
(`src/providers/ai/`) is never persisted either, so it can only appear in a report
generated in the same run that computed it. `None` (the default, and what every
existing caller still gets) renders no summary section at all — never a placeholder.

SDK Validation Sprint (docs/22_SDK_Validation_Sprint.md) — a genuine, previously
unnoticed gap: `Apartment` already carries `platform_id`, `platform_listing_id`,
`currency`, `property_type`, `latitude`/`longitude`, and `last_seen_at` (all populated
by connectors, some since v2.0's first migration), but this generator never rendered
any of them. Platform *name* (not just id) comes from a `platform_registry.get_platform()`
lookup per listing — cheap at typical result-set sizes, and the same read-only pattern
`apartment_repository.get_*` calls already use inside this same transaction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from src.analysis.models import AnalysisResult
from src.core.config import OUTPUT_DIR
from src.discovery import platform_registry
from src.feedback.models import PreferenceProfile
from src.geography.models import GeoEnrichment, TravelMode
from src.ranking_v2.models import RankedApartmentV2
from src.storage import apartment_repository, search_repository
from src.storage.database import Database

_MODE_LABELS = {
    TravelMode.WALKING: "Walking",
    TravelMode.CYCLING: "Cycling",
    TravelMode.DRIVING: "Driving",
    TravelMode.PUBLIC_TRANSPORT: "Public transport",
    TravelMode.STRAIGHT_LINE: "Straight-line",
}


def generate_report(
    db: Database,
    search_id: str,
    output_dir: Path = OUTPUT_DIR,
    analysis_results: dict[str, AnalysisResult] | None = None,
    ai_summary: str | None = None,
    geo_enrichments: dict[str, GeoEnrichment] | None = None,
    ranking_v2_results: list[RankedApartmentV2] | None = None,
    preference_profile: PreferenceProfile | None = None,
) -> Path:
    analysis_results = analysis_results or {}
    geo_enrichments = geo_enrichments or {}
    ranking_v2_by_id = {entry.apartment_id: entry for entry in (ranking_v2_results or [])}

    with db.transaction() as conn:
        search = search_repository.get_search_request(conn, search_id)
        results = search_repository.get_search_results(conn, search_id)

        rows_html = []
        for result in results:
            apartment = apartment_repository.get_apartment(conn, result.apartment_id)
            platform = platform_registry.get_platform(conn, apartment.platform_id)
            images = apartment_repository.get_images(conn, result.apartment_id)
            price_history = apartment_repository.get_price_history(conn, result.apartment_id)
            availability_history = apartment_repository.get_availability_history(conn, result.apartment_id)
            analysis = analysis_results.get(result.apartment_id)
            geo = geo_enrichments.get(result.apartment_id)
            ranking_v2 = ranking_v2_by_id.get(result.apartment_id)
            rows_html.append(
                _render_result(
                    result, apartment, platform, images, price_history, availability_history,
                    analysis, geo, ranking_v2,
                )
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{search_id}.html"
    report_path.write_text(_render_page(search, rows_html, ai_summary, preference_profile), encoding="utf-8")
    return report_path


def _render_page(search, rows_html: list[str], ai_summary: str | None = None, preference_profile: PreferenceProfile | None = None) -> str:
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
  .analysis {{ margin-top: 0.5rem; }}
  .analysis-detail {{ font-size: 0.8rem; color: #444; margin: 0.25rem 0 0; padding-left: 1.2rem; }}
  .analysis-warning {{ color: #a15c00; }}
  .geo {{ margin-top: 0.5rem; }}
  .geo-detail {{ font-size: 0.8rem; color: #444; margin: 0.25rem 0 0; padding-left: 1.2rem; }}
  .ranking-v2 {{ margin-top: 0.5rem; }}
  .ranking-v2-positive {{ color: #1a7a3c; }}
  .ranking-v2-negative {{ color: #a13c3c; }}
  .ai-summary {{ background: #f2f6fb; border: 1px solid #cddcec; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1.5rem; font-size: 0.95rem; }}
  .preferences {{ background: #f7f4ee; border: 1px solid #e0d8c8; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1.5rem; font-size: 0.9rem; }}
  .preferences ul {{ margin: 0.4rem 0 0; padding-left: 1.2rem; }}
  .pref-explicit {{ color: #1a5c8a; }}
  .pref-inferred {{ color: #6b6b6b; }}
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
{_render_ai_summary(ai_summary)}
{_render_preference_profile(preference_profile)}
{''.join(rows_html) if rows_html else '<p>No matching listings.</p>'}
</body>
</html>
"""


def _render_ai_summary(ai_summary: str | None) -> str:
    """Omitted entirely when no AI provider produced a summary (`None`) — never a
    placeholder like "AI summary unavailable," matching the same honesty convention
    `_render_analysis()` already follows for missing analyzer evidence.
    """
    if not ai_summary:
        return ""
    return f'<div class="ai-summary"><strong>AI Summary:</strong> {escape(ai_summary)}</div>'


def _render_result(
    result,
    apartment,
    platform,
    images,
    price_history,
    availability_history,
    analysis: AnalysisResult | None,
    geo: GeoEnrichment | None = None,
    ranking_v2: RankedApartmentV2 | None = None,
) -> str:
    photos_html = "".join(
        f'<img src="{escape(Path(image.local_path).as_uri())}" alt="listing photo">' for image in images
    )
    breakdown_html = ", ".join(f"{escape(k)}: {v:.2f}" for k, v in json.loads(result.score_breakdown_json).items())
    price_trend = " → ".join(f"{entry.price:.0f}" for entry in price_history)
    status_trend = " → ".join(escape(entry.status) for entry in availability_history)

    platform_name = platform.name if platform is not None else apartment.platform_id
    coordinates_text = (
        f"{apartment.latitude:.5f}, {apartment.longitude:.5f}"
        if apartment.latitude is not None and apartment.longitude is not None
        else "n/a"
    )

    return f"""<div class="listing">
  <span class="rank">#{result.rank}</span>
  <h2>{escape(apartment.title)}</h2>
  <div class="price">${result.price_at_search:.0f}/mo — {escape(result.status_at_search)}</div>
  <div class="facts">{apartment.bedrooms or '?'} bed · {apartment.bathrooms or '?'} bath · {apartment.sqft or '?'} sqft · {escape(apartment.address_raw or '')}</div>
  <div class="facts">Score: {result.score:.2f} <span class="score-breakdown">({breakdown_html})</span></div>
  <div class="facts">Platform: {escape(platform_name)} &nbsp;|&nbsp; Listing ID: {escape(apartment.platform_listing_id)} &nbsp;|&nbsp; Property type: {escape(apartment.property_type or 'n/a')} &nbsp;|&nbsp; Currency: {escape(apartment.currency or 'n/a')}</div>
  <div class="facts">Coordinates: {coordinates_text} &nbsp;|&nbsp; Last updated: {escape(apartment.last_seen_at.isoformat())}</div>
  {f'<div class="facts">{escape(apartment.description)}</div>' if apartment.description else ''}
  <div class="photos">{photos_html}</div>
  <div class="history">Price history: {price_trend or 'n/a'} &nbsp;|&nbsp; Availability history: {status_trend or 'n/a'}</div>
  {_render_analysis(analysis)}
  {_render_geo(geo)}
  {_render_ranking_v2(ranking_v2)}
  <div><a href="{escape(apartment.url)}" target="_blank" rel="noopener">Original listing</a></div>
</div>
"""


def _render_analysis(analysis: AnalysisResult | None) -> str:
    """"Reports must display: individual analyzer scores, composite scores, evidence
    summary, warnings, confidence" (v2.0 Step 6 mission) — omitted entirely when no
    analysis is available (see this module's docstring for when that happens).
    """
    if analysis is None:
        return ""

    composite_html = ", ".join(
        f"{escape(composite.name)}: {composite.score:.2f}" if composite.score is not None else f"{escape(composite.name)}: n/a"
        for composite in analysis.composite_scores
    )

    analyzer_rows = []
    for analyzer_result in analysis.analyzer_results:
        if analyzer_result.score is not None:
            score_text = f"{analyzer_result.score:.2f}"
            confidence_text = f"{analyzer_result.confidence:.2f}" if analyzer_result.confidence is not None else "n/a"
        else:
            score_text = "n/a"
            confidence_text = "n/a"
        evidence_text = "; ".join(analyzer_result.evidence) or "—"
        warnings_text = "; ".join(analyzer_result.warnings)
        warnings_html = f' <span class="analysis-warning">⚠ {escape(warnings_text)}</span>' if warnings_text else ""
        analyzer_rows.append(
            f"<li><strong>{escape(analyzer_result.analyzer_name)}</strong>: {score_text} "
            f"(confidence: {confidence_text}) — {escape(evidence_text)}{warnings_html}</li>"
        )

    return f"""<div class="analysis">
    <div class="facts">Composite scores: {composite_html or 'n/a'}</div>
    <ul class="analysis-detail">{''.join(analyzer_rows)}</ul>
  </div>"""


def _render_geo(geo: GeoEnrichment | None) -> str:
    """"Reports must display: walking time, driving time, public transport, nearby
    services, distance summaries, confidence" (v2.5 Step 10 mission) — omitted
    entirely when no `GeoEnrichment` is available (no `geo_engine` was supplied, or
    the apartment had no coordinates/reference point — see
    `GeographicEngine.enrich()`'s own docstring for when that happens), matching the
    same honesty convention `_render_analysis()` already follows.
    """
    if geo is None or (not geo.distances and not any(geo.nearby.values())):
        return ""

    distance_rows = []
    for mode in TravelMode:
        result = geo.distances.get(mode)
        if result is None:
            continue
        distance_text = f"{result.distance_km:.2f} km" if result.distance_km is not None else "n/a"
        time_text = f"{result.travel_time_minutes:.0f} min" if result.travel_time_minutes is not None else "n/a"
        distance_rows.append(
            f"<li><strong>{escape(_MODE_LABELS[mode])}</strong>: {distance_text}"
            f"{' — ' + time_text if result.travel_time_minutes is not None else ''} "
            f"(confidence: {result.confidence:.2f}, {escape(result.calculation_method)})</li>"
        )

    nearby_rows = []
    for category, places in geo.nearby.items():
        for place in places:
            if place.count is None:
                continue
            confidence_text = f"{place.confidence:.2f}" if place.confidence is not None else "n/a"
            nearby_rows.append(
                f"<li><strong>{escape(category)}</strong>: {place.count} nearby (confidence: {confidence_text})</li>"
            )

    return f"""<div class="geo">
    <div class="facts">Distance summary:</div>
    <ul class="geo-detail">{''.join(distance_rows) or '<li>n/a</li>'}</ul>
    <div class="facts">Nearby services:</div>
    <ul class="geo-detail">{''.join(nearby_rows) or '<li>No curated nearby data yet</li>'}</ul>
  </div>"""


def _render_ranking_v2(ranking_v2: RankedApartmentV2 | None) -> str:
    """"Display: Score, Confidence, Evidence, Top Positive Factors, Top Negative
    Factors" (v2.5 Step 11 mission) — omitted entirely when no `RankingEngineV2`
    result is available (no `ranking_engine_v2` was supplied), matching the same
    honesty convention `_render_analysis()`/`_render_geo()` already follow.
    """
    if ranking_v2 is None:
        return ""

    confidence_text = (
        f"{ranking_v2.confidence.overall:.2f}" if ranking_v2.confidence.overall is not None else "n/a"
    )
    positive_html = "".join(f"<li>{escape(reason)}</li>" for reason in ranking_v2.explanation.top_positive_factors)
    negative_html = "".join(f"<li>{escape(reason)}</li>" for reason in ranking_v2.explanation.top_negative_factors)
    warnings_html = (
        f'<div class="facts">⚠ {escape("; ".join(ranking_v2.warnings))}</div>' if ranking_v2.warnings else ""
    )

    return f"""<div class="ranking-v2">
    <div class="facts">Ranking Engine V2 — Score: {ranking_v2.final_score:.1f} (confidence: {confidence_text})</div>
    <ul class="geo-detail ranking-v2-positive">{positive_html or '<li>No standout positive factors</li>'}</ul>
    <ul class="geo-detail ranking-v2-negative">{negative_html or '<li>No standout negative factors</li>'}</ul>
    {warnings_html}
  </div>"""


def _render_preference_profile(preference_profile: "PreferenceProfile | None") -> str:
    """"Add optional report sections showing: why the result matches the user's
    preferences, which preferences were explicit, which preferences were
    inferred, confidence of learned preferences, how ranking would change
    without inferred preferences" (v2.5 Step 12 mission). Omitted entirely when
    no profile was supplied — the same honesty convention every prior optional
    section already follows. Inferred preferences are labeled as such precisely
    so a reader can see which ones would disappear under `EXPLICIT_ONLY` mode —
    without this report needing to re-run ranking a second time to prove it.
    """
    if preference_profile is None:
        return ""

    explicit_rows = []
    inferred_rows = []
    for key, value in sorted(preference_profile.preferences.items()):
        if value.current_value is None:
            continue
        confidence_text = f"{value.confidence.overall:.2f}"
        row = f"<li><strong>{escape(key)}</strong>: {escape(str(value.current_value))} (confidence: {confidence_text})</li>"
        (explicit_rows if value.is_explicit else inferred_rows).append(row)

    return f"""<div class="preferences">
    <div class="facts">Preference Profile ({escape(preference_profile.profile_id)}, mode: {escape(preference_profile.mode.value)})</div>
    <div class="facts pref-explicit">Explicit preferences (always authoritative):</div>
    <ul>{''.join(explicit_rows) or '<li>None set</li>'}</ul>
    <div class="facts pref-inferred">Inferred preferences (would not apply under EXPLICIT_ONLY mode):</div>
    <ul>{''.join(inferred_rows) or '<li>None learned yet</li>'}</ul>
  </div>"""
