"""Pure functions computing the per-search observation metrics defined in
docs/16_Knowledge_Engine.md — no database access, so each is independently
unit-testable. Called from src/knowledge/knowledge_service.py right after a
connector's raw results come back (before normalization: `availability_quality_score`
specifically needs the RAW, pre-normalized status — see its docstring) and, for
`ranking_usefulness_score`, after ranking is complete.
"""

from __future__ import annotations

from src.connectors.base import RawListing
from src.ranking.ranking_engine import RankedApartment
from src.storage.models import Apartment

DEFAULT_TOP_N = 10

_EXPECTED_FIELDS = ("title", "price", "url", "bedrooms", "bathrooms", "sqft", "address_raw")


def extraction_quality_score(raw_listings: list[RawListing]) -> float | None:
    """Average, across this run's listings, of (non-empty expected fields ÷ expected
    fields), expected = {title, price, url, bedrooms, bathrooms, sqft, address_raw}.
    """
    if not raw_listings:
        return None
    return sum(_field_completeness(raw) for raw in raw_listings) / len(raw_listings)


def _field_completeness(raw: RawListing) -> float:
    present = sum(1 for field_name in _EXPECTED_FIELDS if _is_present(getattr(raw, field_name)))
    return present / len(_EXPECTED_FIELDS)


def _is_present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def image_quality_score(raw_listings: list[RawListing]) -> float | None:
    """Fraction of this run's listings with at least one image URL."""
    if not raw_listings:
        return None
    return sum(1 for raw in raw_listings if raw.image_urls) / len(raw_listings)


def availability_quality_score(raw_listings: list[RawListing]) -> float | None:
    """Fraction of listings where the connector actually reported a status, as opposed
    to it being absent and silently defaulted to "available" by `normalizer.py`.
    Computed from the RAW value (`RawListing.status`, which defaults to `None` if a
    connector doesn't set it — see `connectors/base.py`) — the normalized
    `Apartment.current_status` always has a value, which would make this trivially
    100% and useless as a signal.
    """
    if not raw_listings:
        return None
    return sum(1 for raw in raw_listings if raw.status) / len(raw_listings)


def duplicate_rate(raw_listings: list[RawListing]) -> float | None:
    """Fraction of this platform's raw listings in this run that share a
    `platform_listing_id` with another listing in the *same* result set — a connector
    /pagination bug signal, distinct from re-observing an apartment across searches
    (normal) or cross-platform duplicates (V2, unrelated).
    """
    if not raw_listings:
        return None
    ids = [raw.platform_listing_id for raw in raw_listings]
    duplicate_count = len(ids) - len(set(ids))
    return duplicate_count / len(ids)


def ranking_usefulness_score(
    platform_id: str,
    ranked: list[RankedApartment],
    apartments: list[Apartment],
    top_n: int = DEFAULT_TOP_N,
) -> float | None:
    """(platform's fraction of the top-N ranked results) ÷ (platform's fraction of all
    candidate apartments this run). >1 means the platform punched above its weight
    (small volume, disproportionately well-ranked); <1 means high volume but rarely
    competitive. `None` when there's nothing to compare against (no candidates, this
    platform contributed none, or nothing survived ranking).
    """
    total_candidates = len(apartments)
    if total_candidates == 0:
        return None

    candidate_share = sum(1 for apartment in apartments if apartment.platform_id == platform_id) / total_candidates
    if candidate_share == 0:
        return None

    top_n_slice = ranked[:top_n]
    if not top_n_slice:
        return None

    top_n_share = sum(1 for entry in top_n_slice if entry.apartment.platform_id == platform_id) / len(top_n_slice)
    return top_n_share / candidate_share
