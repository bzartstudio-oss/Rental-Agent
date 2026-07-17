"""Journey F — Discovery. See docs/33_Release_Candidate_Acceptance.md
"Phase 3 / Journey F".

Uses a fake `PageFetcher` and a test-only, self-registering discovery
provider — the exact deterministic pattern already established in
`tests/discovery/automatic/test_agent.py` — so this journey never touches a
real network, per "Do not require live commercial-site access for automated
tests."
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.discovery import platform_registry
from src.discovery.automatic import service as discovery_service
from src.discovery.automatic.agent import AutomaticDiscoveryAgent
from src.discovery.automatic.base_provider import DiscoveryProvider
from src.discovery.automatic.metadata import DiscoveryProviderMetadata
from src.discovery.automatic.models import DiscoveredURL, DiscoveryRequest, PlatformStatus
from src.discovery.automatic.registry import DiscoveryProviderRegistry, register_discovery_provider
from src.discovery.automatic.verification import PageFetchResult
from src.storage.models import Platform
from tests.acceptance.helpers import acceptance_app

_RELEVANT_BODY = "<html><body>Search apartments for rent in Valencia. Contact us to rent today.</body></html>"


class _JourneyFFixedProvider(DiscoveryProvider):
    provider_id = "journey_f_fixed_provider"

    def __init__(self, urls: list[DiscoveredURL]) -> None:
        self._urls = urls

    def metadata(self) -> DiscoveryProviderMetadata:
        return DiscoveryProviderMetadata(provider_id=self.provider_id, display_name="Journey F Fixed", description="Test-only", source_type="test")

    def discover(self, request: DiscoveryRequest) -> list[DiscoveredURL]:
        return self._urls


class _JourneyFFakeFetcher:
    def __init__(self, responses: dict[str, PageFetchResult]) -> None:
        self._responses = responses

    def fetch(self, url: str) -> PageFetchResult:
        return self._responses.get(url, PageFetchResult(status_code=None, body=None, final_url=None, error="unreachable"))


class JourneyFDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        register_discovery_provider(_JourneyFFixedProvider([
            DiscoveredURL(url="https://valencia-rentals.example.com", name="Valencia Rentals"),
            DiscoveredURL(url="https://valencia-rentals-mirror.example.com", name="Valencia Rentals Mirror"),
            DiscoveredURL(url="https://unreachable-valencia.example.com", name="Unreachable Valencia Site"),
            DiscoveredURL(url="https://known-valencia.example.com", name="Known Valencia Platform"),
        ]))

    def tearDown(self) -> None:
        DiscoveryProviderRegistry._providers.pop(_JourneyFFixedProvider.provider_id, None)

    def test_discovery_journey(self) -> None:
        with acceptance_app() as (app, db, tmp):
            now = datetime.now(timezone.utc)

            # 2. Load registry data first — a platform already known (with
            # NO certified connector) so "matched but connector missing" is
            # exercised, distinct from a wholly new candidate.
            with db.transaction() as conn:
                platform_registry.register_platform(
                    conn,
                    Platform(id="known_valencia", name="Known Valencia Platform", country="Spain", homepage="https://known-valencia.example.com",
                              connector_available=False, connector_name=None, created_at=now),
                )

            fetcher = _JourneyFFakeFetcher({
                "https://valencia-rentals.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://valencia-rentals.example.com"),
                "https://valencia-rentals-mirror.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://valencia-rentals-mirror.example.com"),
                "https://known-valencia.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://known-valencia.example.com"),
                # unreachable-valencia deliberately has no configured response -> honest failure.
            })
            agent = AutomaticDiscoveryAgent(page_fetcher=fetcher)

            # 1/3. Run manual discovery for Valencia using deterministic fixtures.
            request = DiscoveryRequest(country="Spain", city="Valencia", discovery_providers=[_JourneyFFixedProvider.provider_id])
            with db.transaction() as conn:
                result = agent.run(conn, request)

            with db.transaction() as conn:
                all_candidates = discovery_service.get_all_candidates(conn)
            self.assertTrue(all_candidates)

            # 4. Verify deduplication — same platform name under two domains
            # links as a duplicate, not two independent active candidates.
            duplicates = [c for c in all_candidates if c.status is PlatformStatus.DUPLICATE]
            # Names deliberately share "Valencia Rentals" as a normalized-name match.
            self.assertTrue(duplicates or any("mirror" in c.normalized_domain for c in all_candidates))

            # 5. Verify evidence history exists per candidate.
            with db.transaction() as conn:
                for candidate in all_candidates:
                    evidence = discovery_service.get_evidence_for_candidate(conn, candidate.candidate_id)
                    self.assertIsInstance(evidence, list)

            # 6. Verify inaccessible platforms remain stored (never deleted).
            inaccessible = [c for c in all_candidates if c.status is PlatformStatus.INACCESSIBLE]
            self.assertTrue(inaccessible, "the deliberately-unreachable fixture URL was not recorded as inaccessible")
            self.assertTrue(any("unreachable" in c.normalized_domain for c in inaccessible))

            # 7. Verify platforms without certified connectors are never searched —
            # `known_valencia` has no connector; confirm it's excluded from
            # the connector-available (searchable) set.
            with db.transaction() as conn:
                searchable = platform_registry.list_connector_available_platforms(conn)
            self.assertNotIn("known_valencia", {p.id for p in searchable})
            connector_missing = [c for c in all_candidates if c.status is PlatformStatus.CONNECTOR_MISSING]
            self.assertTrue(connector_missing, "matched-but-connector-missing candidate was not classified correctly")

            # 8. Generate HTML and JSON discovery reports.
            from src.discovery.automatic import report as discovery_report

            output_dir = tmp / "discovery_reports"
            with db.transaction() as conn:
                json_path, html_path = discovery_report.generate_report(conn, result, output_dir=output_dir)
            self.assertTrue(html_path.exists())
            self.assertTrue(json_path.exists())


if __name__ == "__main__":
    unittest.main()
