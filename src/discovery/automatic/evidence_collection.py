"""Turns one discovered URL + its (optional) fetched homepage into the mission's
own 15 named `PlatformEvidence` entries. See
docs/29_Automatic_Platform_Discovery.md "Platform Evidence" — "Never overwrite
evidence": every call here only ever appends new `PlatformEvidence` rows,
never edits or removes one.

Two of the mission's 15 evidence "fields" (`dates`, `confidence`) are already
first-class fields on `PlatformEvidence` itself (`collected_at`, `confidence`)
rather than a redundant thirteenth/fourteenth evidence_type string — every
other named field below gets its own `evidence_type`.

Deliberately no HTML parser dependency: `_extract_title`/`_extract_meta_description`/
`_extract_html_lang` are small, honest regexes over an already-fetched body —
never a second network call, never JavaScript execution.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from src.discovery.automatic.models import DiscoveredURL, DiscoveryRequest, PlatformEvidence
from src.discovery.automatic.verification import PageFetchResult

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESCRIPTION_RE = re.compile(
    r"""<meta[^>]+name=["']description["'][^>]+content=["'](.*?)["']""", re.IGNORECASE | re.DOTALL
)
_HTML_LANG_RE = re.compile(r"""<html[^>]+lang=["']([a-zA-Z-]+)["']""", re.IGNORECASE)


def collect_evidence(
    candidate_id: str,
    run_id: str,
    discovered: DiscoveredURL,
    provider_id: str,
    fetch_result: PageFetchResult | None,
    request: DiscoveryRequest,
    *,
    now: datetime | None = None,
) -> list[PlatformEvidence]:
    now = now or datetime.now(timezone.utc)
    body_lower = fetch_result.body.lower() if (fetch_result and fetch_result.body) else None

    evidence = [
        _make(candidate_id, run_id, provider_id, "discovered_url", {"url": discovered.url}, now),
        _make(candidate_id, run_id, provider_id, "provider", {"provider_id": provider_id}, now),
    ]

    if discovered.source_hint:
        evidence.append(
            _make(candidate_id, run_id, provider_id, "search_phrase_or_seed_source", {"source_hint": discovered.source_hint}, now)
        )

    title = _extract_title(fetch_result.body) if fetch_result and fetch_result.body else None
    if title:
        evidence.append(_make(candidate_id, run_id, provider_id, "page_title", {"title": title}, now))

    description = _extract_meta_description(fetch_result.body) if fetch_result and fetch_result.body else None
    if description:
        evidence.append(_make(candidate_id, run_id, provider_id, "page_description", {"description": description}, now))

    if discovered.name:
        evidence.append(_make(candidate_id, run_id, provider_id, "keywords", {"name": discovered.name}, now))

    if body_lower is not None:
        location_terms = [term for term in (request.country, request.region, request.city) if term]
        matched_locations = [term for term in location_terms if term.lower() in body_lower]
        if matched_locations:
            evidence.append(
                _make(candidate_id, run_id, provider_id, "location_evidence", {"matched_locations": matched_locations}, now)
            )

        matched_categories = [c for c in request.rental_categories if c.lower() in body_lower]
        if matched_categories:
            evidence.append(
                _make(candidate_id, run_id, provider_id, "rental_category_evidence", {"matched_categories": matched_categories}, now)
            )

    if fetch_result and fetch_result.body:
        html_lang = _extract_html_lang(fetch_result.body)
        if html_lang:
            evidence.append(_make(candidate_id, run_id, provider_id, "language_evidence", {"html_lang": html_lang}, now))

    evidence.append(
        _make(
            candidate_id, run_id, provider_id, "robots_or_policy_observation",
            {"checked": False, "reason": "robots.txt/access-policy fetch is out of scope this sprint"}, now,
        )
    )

    if fetch_result is not None:
        evidence.append(
            _make(
                candidate_id, run_id, provider_id, "raw_evidence_reference",
                {"final_url": fetch_result.final_url, "status_code": fetch_result.status_code, "error": fetch_result.error}, now,
            )
        )

    return evidence


def evidence_text_for_classification(discovered: DiscoveredURL, fetch_result: PageFetchResult | None) -> str:
    """The concatenated, lowercased text `classification.classify_candidate()` scores
    against — name/source hint plus title/description when a homepage was fetched.
    """
    parts = [discovered.name or "", discovered.source_hint or ""]
    if fetch_result and fetch_result.body:
        title = _extract_title(fetch_result.body)
        description = _extract_meta_description(fetch_result.body)
        parts.append(title or "")
        parts.append(description or "")
    return " ".join(parts)


def _make(candidate_id: str, run_id: str, provider_id: str, evidence_type: str, value: dict, now: datetime) -> PlatformEvidence:
    return PlatformEvidence(
        candidate_id=candidate_id, run_id=run_id, evidence_type=evidence_type,
        discovery_provider=provider_id, value=value, collected_at=now,
    )


def _extract_title(body: str) -> str | None:
    match = _TITLE_RE.search(body)
    return match.group(1).strip() or None if match else None


def _extract_meta_description(body: str) -> str | None:
    match = _META_DESCRIPTION_RE.search(body)
    return match.group(1).strip() or None if match else None


def _extract_html_lang(body: str) -> str | None:
    match = _HTML_LANG_RE.search(body)
    return match.group(1) if match else None
