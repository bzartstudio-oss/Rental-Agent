"""Heuristic capability estimation. See docs/29_Automatic_Platform_Discovery.md
"Capability Estimation" — the mission's own 14 named capabilities, every one of
them "clearly marked as an estimate until confirmed by a connector" (the
mission's own words): nothing here is ever written back as a confirmed fact,
and `PlatformCapabilityEstimate.is_estimate` defaults to `True` and is never
overridden.

Estimates are cheap keyword/marker checks against an already-fetched homepage
body — never a second network call, never JavaScript execution. `requires_login`
is deliberately NOT re-detected here; it's passed in from
`verification.verify_homepage_content()`'s own result so the two modules never
disagree about the same finding.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.discovery.automatic.models import PlatformCapabilityEstimate

# One small, documented marker set per capability — declared in the same order
# as the mission's own CAPABILITY ESTIMATION list (minus requires_login, which
# is supplied by the caller, and likely_connector_complexity, which is derived).
_CAPABILITY_MARKERS: dict[str, tuple[str, ...]] = {
    "images": ("<img", "photo", "gallery"),
    "prices": ("price", "€", "$", "£", "/mo", "per month"),
    "availability": ("available", "availability", "move-in", "vacant"),
    "coordinates": ("latitude", "longitude", "geojson", "data-lat"),
    "addresses": ("address", "street", "calle", "avenida"),
    "descriptions": ("<meta name=\"description\"", "description"),
    "property_types": ("apartment", "studio", "house", "room", "flat", "villa"),
    "room_sharing": ("flatshare", "roommate", "shared room", "room to rent"),
    "pagination": ("next page", "pagination", "rel=\"next\"", "page="),
    "search_filters": ("filter", "sort by", "price range", "bedrooms"),
    "saved_searches": ("save search", "save this search", "email alert", "saved searches"),
    "api_or_feed": ("/api", "rss", "atom feed", ".json", "/feed"),
    "requires_javascript": ("<noscript", "react", "vue.js", "angular", "window.__"),
}

_CAPABILITY_KEYS_IN_ORDER = (
    "images", "prices", "availability", "coordinates", "addresses", "descriptions",
    "property_types", "room_sharing", "pagination", "search_filters", "saved_searches",
    "api_or_feed", "requires_javascript", "requires_login", "likely_connector_complexity",
)


def estimate_capabilities(
    candidate_id: str,
    page_body: str | None,
    login_requirement: str,
    *,
    now: datetime | None = None,
) -> list[PlatformCapabilityEstimate]:
    """Returns one `PlatformCapabilityEstimate` per capability key, in mission
    order. `page_body=None` (nothing was fetched) yields honest "unknown"
    estimates for every marker-based capability rather than a fabricated guess.
    """
    now = now or datetime.now(timezone.utc)
    body_lower = page_body.lower() if page_body is not None else None

    estimates: list[PlatformCapabilityEstimate] = []
    marker_hits: dict[str, list[str]] = {}

    for capability_key in _CAPABILITY_MARKERS:
        markers = _CAPABILITY_MARKERS[capability_key]
        if body_lower is None:
            estimated_value = {"present": None, "matched_markers": [], "confidence": "unknown"}
        else:
            matched = [marker for marker in markers if marker in body_lower]
            marker_hits[capability_key] = matched
            estimated_value = {
                "present": len(matched) > 0,
                "matched_markers": matched,
                "confidence": "low",
            }
        estimates.append(
            PlatformCapabilityEstimate(
                candidate_id=candidate_id, capability_key=capability_key,
                estimated_value=estimated_value, observed_at=now,
            )
        )

    estimates.append(
        PlatformCapabilityEstimate(
            candidate_id=candidate_id, capability_key="requires_login",
            estimated_value={"login_requirement": login_requirement}, observed_at=now,
        )
    )

    estimates.append(
        _estimate_connector_complexity(candidate_id, body_lower, login_requirement, marker_hits, now)
    )

    return estimates


def _estimate_connector_complexity(
    candidate_id: str,
    body_lower: str | None,
    login_requirement: str,
    marker_hits: dict[str, list[str]],
    now: datetime,
) -> PlatformCapabilityEstimate:
    """A simple, explainable rule-of-thumb — never a scored/trained model. "Low"
    when the platform advertises an API/feed and shows no JavaScript-heavy or
    login-gated markers; "high" when both JavaScript rendering and a login wall
    are indicated; "medium" otherwise. `"unknown"` when nothing was fetched.
    """
    if body_lower is None:
        estimated_value = {"level": "unknown", "reasons": ["no homepage content was fetched"]}
        return PlatformCapabilityEstimate(
            candidate_id=candidate_id, capability_key="likely_connector_complexity",
            estimated_value=estimated_value, observed_at=now,
        )

    has_api_or_feed = bool(marker_hits.get("api_or_feed"))
    has_javascript_markers = bool(marker_hits.get("requires_javascript"))
    requires_login = login_requirement == "login_required"

    reasons = []
    if has_api_or_feed:
        reasons.append("an API/feed appears to be advertised")
    if has_javascript_markers:
        reasons.append("homepage shows JavaScript-rendering markers")
    if requires_login:
        reasons.append("homepage appears to require login")

    if has_api_or_feed and not has_javascript_markers and not requires_login:
        level = "low"
    elif has_javascript_markers and requires_login:
        level = "high"
    else:
        level = "medium"

    if not reasons:
        reasons.append("no strong complexity signals were found")

    return PlatformCapabilityEstimate(
        candidate_id=candidate_id, capability_key="likely_connector_complexity",
        estimated_value={"level": level, "reasons": reasons}, observed_at=now,
    )
