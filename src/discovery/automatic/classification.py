"""Deterministic, explainable platform classification. See
docs/29_Automatic_Platform_Discovery.md "Classification" — "Classification must
be deterministic and explainable. Do not use opaque machine learning" (the
mission's own words): every classification here is a fixed keyword-scoring rule
over already-collected evidence, never a trained model.

Each of the mission's 13 categories has one small, documented keyword set; a
candidate's homepage text/evidence is scored against every category and the
highest-scoring match wins (ties broken by category declaration order, making
the result fully reproducible). `UNKNOWN` when nothing scores above zero —
never a fabricated guess.
"""

from __future__ import annotations

from src.discovery.automatic.models import PlatformClassification

# Order matters only for deterministic tie-breaking — declared in the same order
# as the mission's own PLATFORM CLASSIFICATION list.
_CATEGORY_KEYWORDS: dict[PlatformClassification, tuple[str, ...]] = {
    PlatformClassification.RENTAL_MARKETPLACE: ("rent", "rental", "apartments for rent", "find a rental"),
    PlatformClassification.PROPERTY_PORTAL: ("property portal", "real estate", "properties", "listings"),
    PlatformClassification.SHARED_HOUSING_PLATFORM: ("flatshare", "roommate", "shared housing", "shared flat", "room to rent"),
    PlatformClassification.STUDENT_HOUSING_PLATFORM: ("student housing", "student accommodation", "university housing", "student residence"),
    PlatformClassification.LOCAL_AGENCY: ("estate agency", "real estate agency", "inmobiliaria", "letting agent"),
    PlatformClassification.PROPERTY_MANAGER: ("property management", "property manager", "managed by"),
    PlatformClassification.AGGREGATOR: ("compare listings", "search all", "aggregator", "meta search"),
    PlatformClassification.CLASSIFIEDS: ("classifieds", "classified ads", "buy and sell", "marketplace ads"),
    PlatformClassification.SOCIAL_OR_COMMUNITY_SOURCE: ("community group", "forum", "facebook group", "social network"),
    PlatformClassification.COMMERCIAL_PROPERTY_PLATFORM: ("commercial property", "office space", "retail space", "warehouse for rent"),
    PlatformClassification.VACATION_RENTAL_PLATFORM: ("vacation rental", "holiday rental", "short-term stay", "nightly rate"),
}


def classify_candidate(evidence_text: str) -> tuple[PlatformClassification, dict[str, int]]:
    """Scores `evidence_text` (already-lowercased page title/description/keywords,
    concatenated) against every category's keyword set. Returns the winning
    category plus every category's raw score, so the decision is fully
    inspectable — "Classification must be ... explainable."
    """
    text = evidence_text.lower()
    scores: dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        scores[category.value] = sum(1 for keyword in keywords if keyword in text)

    best_category, best_score = max(
        ((category, scores[category.value]) for category in _CATEGORY_KEYWORDS), key=lambda pair: pair[1],
    )
    if best_score <= 0:
        return PlatformClassification.UNKNOWN, scores
    return best_category, scores


def explain_classification(classification: PlatformClassification, scores: dict[str, int]) -> str:
    if classification in (PlatformClassification.UNKNOWN, PlatformClassification.IRRELEVANT):
        return f"No category keywords matched — classified as {classification.value}"
    winning_score = scores.get(classification.value, 0)
    return f"Classified as {classification.value} ({winning_score} matching keyword(s))"
