"""DiscoveryAgent — the Multi-Platform Discovery Framework (docs/05_Platform_Discovery.md).

Two responsibilities, kept as separate methods because different callers need them at
different times:

- `discover(request)` — search-facing. Called by core/agent.py for every real search;
  returns only platforms this system can actually query (connector_available = True).
- `sync_platforms(candidates)` — management-facing. Called whenever new/updated platform
  metadata is available (in v1.1, by ui/cli.py against a static seed list — see
  discovery/known_platforms.py). Loads existing platforms, detects duplicates, updates
  metadata for matches, saves genuinely new platforms, and marks unsupported ones —
  the five behaviors required of the framework.

No listings are scraped here, in either method — only platform-level metadata ever
passes through this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from src.discovery import platform_registry
from src.storage.database import Database
from src.storage.models import Platform


@dataclass
class PlatformCandidate:
    """Platform metadata pending registration — the input to sync_platforms(). Distinct
    from storage.models.Platform because a candidate has no `id` guarantee of matching an
    existing row yet (that's exactly what duplicate detection figures out) and no
    `created_at` (only assigned if it turns out to be genuinely new).
    """

    platform_id: str
    name: str
    country: str
    homepage: str
    supported_cities: list[str] = field(default_factory=list)
    rental_types: list[str] = field(default_factory=list)
    search_url: str | None = None
    requires_login: bool = False
    connector_available: bool = False
    connector_name: str | None = None
    discovery_method: str = "manual"
    notes: str | None = None


@dataclass
class DiscoveryReport:
    """Summarizes what sync_platforms() did, by platform id."""

    new_platforms: list[str] = field(default_factory=list)
    updated_platforms: list[str] = field(default_factory=list)
    duplicate_candidate_ids: list[str] = field(default_factory=list)
    marked_unsupported: list[str] = field(default_factory=list)


class DiscoveryAgent:
    def __init__(self, db: Database) -> None:
        self._db = db

    def discover(self, request: object = None) -> list[Platform]:
        """Return the platforms relevant to `request` that this system can actually
        search. V1.1: every platform with a connector, regardless of what `request`
        contains — see docs/05_Platform_Discovery.md. `request` is accepted now so this
        signature doesn't need to change once per-request platform filtering is built.
        """
        with self._db.transaction() as conn:
            return platform_registry.list_connector_available_platforms(conn)

    def load_platforms(self) -> list[Platform]:
        """Every known platform, connector or not — behavior 1 (docs/05_Platform_Discovery.md)."""
        with self._db.transaction() as conn:
            return platform_registry.list_all_platforms(conn)

    def sync_platforms(self, candidates: list[PlatformCandidate]) -> DiscoveryReport:
        """Runs all five discovery-framework behaviors over `candidates` in one
        transaction: load existing, detect duplicates, update metadata for matches, save
        new platforms, and mark unsupported ones. See docs/05_Platform_Discovery.md.
        """
        report = DiscoveryReport()
        now = datetime.now(timezone.utc)

        with self._db.transaction() as conn:
            existing = platform_registry.list_all_platforms(conn)  # behavior 1: load existing

            for candidate in candidates:
                duplicate = _find_duplicate(existing, candidate)  # behavior 2: detect duplicates

                if duplicate is not None:
                    updated = _apply_candidate(duplicate, candidate, verified_at=now)
                    platform_registry.update_platform_metadata(conn, duplicate.id, updated)  # behavior 3
                    report.updated_platforms.append(duplicate.id)
                    if candidate.platform_id != duplicate.id:
                        report.duplicate_candidate_ids.append(candidate.platform_id)
                    if not updated.connector_available:
                        report.marked_unsupported.append(duplicate.id)  # behavior 5
                    existing = [updated if p.id == duplicate.id else p for p in existing]
                    continue

                platform = _candidate_to_platform(candidate, verified_at=now, created_at=now)
                platform_registry.register_platform(conn, platform)  # behavior 4: save new
                existing.append(platform)  # so later candidates in this batch can dedupe against it
                report.new_platforms.append(platform.id)
                if not platform.connector_available:
                    report.marked_unsupported.append(platform.id)  # behavior 5

        return report


def normalize_homepage(url: str) -> str:
    """Strip scheme/`www.`/trailing slash so http://www.example.com and
    https://example.com/ compare equal. Deliberately simple — see
    docs/05_Platform_Discovery.md "Why Not Fuzzy Matching". Public (not
    underscore-prefixed) since v2.5 Step 13's `discovery.automatic.normalization`
    reuses this exact function rather than reimplementing the same algorithm.
    """
    parsed = urlparse(url if "://" in url else f"//{url}")
    host = (parsed.netloc or parsed.path).lower()
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip("/")


def _find_duplicate(existing: list[Platform], candidate: PlatformCandidate) -> Platform | None:
    for platform in existing:
        if platform.id == candidate.platform_id:
            return platform
        if normalize_homepage(platform.homepage) == normalize_homepage(candidate.homepage):
            return platform
    return None


def _candidate_to_platform(candidate: PlatformCandidate, verified_at: datetime, created_at: datetime) -> Platform:
    return Platform(
        id=candidate.platform_id,
        name=candidate.name,
        country=candidate.country,
        homepage=candidate.homepage,
        connector_available=candidate.connector_available,
        supported_cities=candidate.supported_cities,
        rental_types=candidate.rental_types,
        search_url=candidate.search_url,
        requires_login=candidate.requires_login,
        connector_name=candidate.connector_name,
        last_verified=verified_at,
        discovery_method=candidate.discovery_method,
        notes=candidate.notes,
        created_at=created_at,
    )


def _apply_candidate(existing: Platform, candidate: PlatformCandidate, verified_at: datetime) -> Platform:
    """Existing platform + fresh candidate data -> updated Platform, keeping `id` and
    `created_at` (identity/history), refreshing everything else.
    """
    return Platform(
        id=existing.id,
        name=candidate.name,
        country=candidate.country,
        homepage=candidate.homepage,
        connector_available=candidate.connector_available,
        supported_cities=candidate.supported_cities,
        rental_types=candidate.rental_types,
        search_url=candidate.search_url,
        requires_login=candidate.requires_login,
        connector_name=candidate.connector_name,
        last_verified=verified_at,
        discovery_method=candidate.discovery_method,
        notes=candidate.notes,
        created_at=existing.created_at,
    )
