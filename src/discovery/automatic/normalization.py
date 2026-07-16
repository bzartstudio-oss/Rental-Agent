"""Domain normalization and candidate deduplication — "Normalize domains and
platform names" / "Remove duplicate candidates" (the mission's own workflow
steps). See docs/29_Automatic_Platform_Discovery.md "Deduplication".

Reuses `discovery.discovery_agent.normalize_homepage()` directly rather than
reimplementing the same domain-normalization algorithm a second time — the
existing Multi-Platform Discovery Framework and this new agent must agree on
what "the same domain" means.
"""

from __future__ import annotations

from src.discovery.discovery_agent import normalize_homepage
from src.discovery.automatic.models import PlatformCandidate

# A caller-configurable set of aliases for domains that are genuinely the same
# platform under a different root (e.g. a country-specific TLD) — "canonical
# domain aliases" (the mission's own words). Empty by default; real alias pairs
# are a curation decision outside this sprint's scope, not hardcoded here.
DOMAIN_ALIASES: dict[str, str] = {}


def normalize_domain(url: str) -> str:
    """The canonical form used for deduplication — reuses
    `discovery_agent.normalize_homepage()`, then resolves any configured alias to
    its canonical target.
    """
    domain = normalize_homepage(url)
    return DOMAIN_ALIASES.get(domain, domain)


def normalize_name(name: str) -> str:
    """A loose, case/whitespace-insensitive form for name-based duplicate
    detection — deliberately simple (no fuzzy matching), the same
    "Why Not Fuzzy Matching" reasoning `docs/05_Platform_Discovery.md` already
    established for homepage comparison.
    """
    return " ".join(name.strip().lower().split())


def find_duplicate_candidate(
    existing: list[PlatformCandidate], normalized_domain: str
) -> PlatformCandidate | None:
    """The primary identity check — matches on normalized root domain (including
    configured aliases). A match here means "the same candidate row, seen again,"
    not a second row needing a duplicate link — Manually configured aliases and
    redirect destinations are folded into `normalize_domain()` itself, so every
    caller compares candidates the same way.
    """
    for candidate in existing:
        if candidate.normalized_domain == normalized_domain:
            return candidate
    return None


def find_duplicate_candidate_by_name(
    existing: list[PlatformCandidate], normalized_name: str, exclude_candidate_id: str
) -> PlatformCandidate | None:
    """The secondary duplicate check — "platform name normalization" (the
    mission's own separate dedup key), used only when two *different* normalized
    domains still look like the same platform by name. Unlike
    `find_duplicate_candidate()`, a match here means the newer row is a genuine
    duplicate of an older, independent one — see `agent.py`'s dedup step, which
    records a `PlatformDuplicateLinkRecord` rather than collapsing the two rows.
    """
    for candidate in existing:
        if candidate.candidate_id == exclude_candidate_id:
            continue
        if normalize_name(candidate.name) == normalized_name:
            return candidate
    return None
