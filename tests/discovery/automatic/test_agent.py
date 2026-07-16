"""Tests for `AutomaticDiscoveryAgent` — the full 12-step pipeline. Uses a fake
`PageFetcher` throughout ("Do not use uncontrolled scraping in tests" — the
mission's own words) and a dedicated, self-cleaning test-only discovery
provider so exact candidate sets are deterministic and independent of the
real `curated_seed`/`manual_url` providers or any live network access.

Covers the mission's own explicit "test that" checklist: existing registry
checked first, duplicates don't create separate active platforms, unsupported
platforms remain stored, failed verification doesn't delete evidence, a
platform without a connector never becomes research-active, and repeated runs
accumulate history.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.discovery.automatic import service
from src.discovery.automatic.agent import AutomaticDiscoveryAgent
from src.discovery.automatic.base_provider import DiscoveryProvider
from src.discovery.automatic.metadata import DiscoveryProviderMetadata
from src.discovery.automatic.models import DiscoveredURL, DiscoveryPolicy, DiscoveryRequest
from src.discovery.automatic.registry import DiscoveryProviderRegistry, register_discovery_provider
from src.discovery.automatic.verification import PageFetchResult
from src.storage.database import Database
from src.storage.models import Platform

_NOW = datetime.now(timezone.utc)


class _FixedURLProvider(DiscoveryProvider):
    """A test-only provider returning an exact, caller-controlled list of URLs —
    lets each test assert exact candidate counts without depending on the real
    `curated_seed` seed list (which can change) or any network access.
    """

    provider_id = "fixed_test_provider"

    def __init__(self, urls: list[DiscoveredURL]) -> None:
        self._urls = urls

    def metadata(self) -> DiscoveryProviderMetadata:
        return DiscoveryProviderMetadata(
            provider_id=self.provider_id, display_name="Fixed", description="Test-only", source_type="test",
        )

    def discover(self, request: DiscoveryRequest) -> list[DiscoveredURL]:
        return self._urls


class _FakeFetcher:
    """Returns a canned `PageFetchResult` per URL, falling back to an "unreachable"
    result for anything not explicitly configured.
    """

    def __init__(self, responses: dict[str, PageFetchResult]) -> None:
        self._responses = responses

    def fetch(self, url: str) -> PageFetchResult:
        return self._responses.get(url, PageFetchResult(status_code=None, body=None, final_url=None, error="not configured"))


_RELEVANT_BODY = "<html><title>Great Rentals</title>Apartments for rent in Valencia, browse listings now</html>"


class _AgentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self._previously_registered = dict(DiscoveryProviderRegistry._providers)

    def tearDown(self) -> None:
        DiscoveryProviderRegistry._providers = self._previously_registered
        self._tmp_dir.cleanup()

    def _register_fixed_provider(self, urls: list[DiscoveredURL]) -> None:
        register_discovery_provider(_FixedURLProvider(urls))

    def _request(self, **overrides) -> DiscoveryRequest:
        defaults = dict(
            country="Spain", region="Valencia", city="Valencia", rental_categories=["apartment"],
            discovery_providers=["fixed_test_provider"],
            refresh_policy=DiscoveryPolicy(force_refresh=True),
        )
        defaults.update(overrides)
        return DiscoveryRequest(**defaults)


class ExistingRegistryCheckedFirstTests(_AgentTestCase):
    def test_matched_existing_platform_with_registered_connector_is_supported(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="demo_platform_registry_entry", name="Demo Platform", country="N/A",
                    homepage="https://demo.example.com", connector_available=True, connector_name="demo_platform",
                ),
            )
        self._register_fixed_provider([DiscoveredURL(url="https://demo.example.com", name="Demo Platform")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({"https://demo.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://demo.example.com")}))

        with self.db.transaction() as conn:
            result = agent.run(conn, self._request())

        self.assertEqual(len(result.supported), 1)
        self.assertEqual(result.supported[0].matched_platform_id, "demo_platform_registry_entry")

    def test_matched_existing_platform_without_connector_is_connector_missing_not_supported(self) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id="known_no_connector", name="Known Platform", country="Spain",
                    homepage="https://known.example.com", connector_available=False,
                ),
            )
        self._register_fixed_provider([DiscoveredURL(url="https://known.example.com", name="Known Platform")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({"https://known.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://known.example.com")}))

        with self.db.transaction() as conn:
            result = agent.run(conn, self._request())

        self.assertEqual(len(result.supported), 0)
        self.assertEqual(result.unsupported[0].status.value, "connector_missing")


class PlatformWithoutConnectorNeverActiveTests(_AgentTestCase):
    def test_a_genuinely_new_relevant_candidate_never_becomes_connector_available(self) -> None:
        self._register_fixed_provider([DiscoveredURL(url="https://newsite.example.com", name="New Site")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({"https://newsite.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://newsite.example.com")}))

        with self.db.transaction() as conn:
            result = agent.run(conn, self._request())

        self.assertEqual(len(result.supported), 0)
        self.assertEqual(result.unsupported[0].status.value, "relevant")


class UnsupportedPlatformsRemainStoredTests(_AgentTestCase):
    def test_unsupported_candidate_is_still_present_after_the_run(self) -> None:
        self._register_fixed_provider([DiscoveredURL(url="https://unsupported.example.com", name="Unsupported")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({"https://unsupported.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://unsupported.example.com")}))

        with self.db.transaction() as conn:
            agent.run(conn, self._request())
            all_candidates = service.get_all_candidates(conn)

        self.assertEqual(len(all_candidates), 1)
        self.assertEqual(all_candidates[0].status.value, "relevant")


class FailedVerificationDoesNotDeleteEvidenceTests(_AgentTestCase):
    def test_inaccessible_candidate_keeps_its_evidence_and_row(self) -> None:
        self._register_fixed_provider([DiscoveredURL(url="https://down.example.com", name="Down Site")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({}))  # unconfigured -> honest fetch error

        with self.db.transaction() as conn:
            result = agent.run(conn, self._request())
            candidate_id = result.unsupported[0].candidate_id
            evidence = service.get_evidence_for_candidate(conn, candidate_id)
            still_there = service.get_candidate(conn, candidate_id)

        self.assertEqual(result.unsupported[0].status.value, "inaccessible")
        self.assertGreater(len(evidence), 0)
        self.assertIsNotNone(still_there)


class DuplicatesDontCreateSeparateActivePlatformsTests(_AgentTestCase):
    def test_same_normalized_domain_discovered_twice_collapses_to_one_row(self) -> None:
        self._register_fixed_provider([
            DiscoveredURL(url="https://www.samesite.example.com/", name="Same Site"),
            DiscoveredURL(url="https://samesite.example.com", name="Same Site Again"),
        ])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({
            "https://www.samesite.example.com/": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://samesite.example.com"),
            "https://samesite.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://samesite.example.com"),
        }))

        with self.db.transaction() as conn:
            agent.run(conn, self._request())
            all_candidates = service.get_all_candidates(conn)

        self.assertEqual(len(all_candidates), 1)  # same normalized domain -> one row, not two

    def test_different_domain_same_name_is_linked_as_a_duplicate(self) -> None:
        self._register_fixed_provider([DiscoveredURL(url="https://original.example.com", name="Twin Platform")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({
            "https://original.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://original.example.com"),
        }))
        with self.db.transaction() as conn:
            agent.run(conn, self._request())

        self._register_fixed_provider([DiscoveredURL(url="https://mirror.example.com", name="Twin Platform")])
        agent2 = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({
            "https://mirror.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://mirror.example.com"),
        }))
        with self.db.transaction() as conn:
            result = agent2.run(conn, self._request())

        self.assertEqual(len(result.duplicates), 1)
        self.assertEqual(result.duplicates[0].status.value, "duplicate")
        with self.db.transaction() as conn:
            links = service.get_duplicate_links(conn, result.duplicates[0].candidate_id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].matched_by, "normalized_name")


class RepeatedRunsAccumulateHistoryTests(_AgentTestCase):
    def test_two_runs_produce_two_history_entries_and_one_persisted_candidate(self) -> None:
        self._register_fixed_provider([DiscoveredURL(url="https://persistent.example.com", name="Persistent Site")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({
            "https://persistent.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://persistent.example.com"),
        }))

        with self.db.transaction() as conn:
            agent.run(conn, self._request())
            agent.run(conn, self._request())
            history = agent.discovery_history(conn)
            all_candidates = service.get_all_candidates(conn)

        self.assertEqual(len(history), 2)
        self.assertEqual(len(all_candidates), 1)  # re-discovered, not duplicated

    def test_refresh_policy_skips_provider_run_within_the_freshness_window(self) -> None:
        self._register_fixed_provider([DiscoveredURL(url="https://persistent.example.com", name="Persistent Site")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({
            "https://persistent.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://persistent.example.com"),
        }))

        with self.db.transaction() as conn:
            agent.run(conn, self._request())
            second = agent.run(conn, self._request(refresh_policy=DiscoveryPolicy(max_age_days=30.0, force_refresh=False)))

        self.assertEqual(second.run.providers_used, [])
        self.assertTrue(any("providers were not re-run" in w for w in second.warnings))


class ProviderFailureIsolationTests(_AgentTestCase):
    def test_one_failing_provider_does_not_abort_the_whole_run(self) -> None:
        class _BrokenProvider(DiscoveryProvider):
            provider_id = "broken_test_provider"

            def metadata(self) -> DiscoveryProviderMetadata:
                return DiscoveryProviderMetadata(provider_id=self.provider_id, display_name="Broken", description="", source_type="test")

            def discover(self, request: DiscoveryRequest) -> list[DiscoveredURL]:
                from src.discovery.automatic.exceptions import DiscoveryProviderError
                raise DiscoveryProviderError("simulated provider failure")

        register_discovery_provider(_BrokenProvider())
        self._register_fixed_provider([DiscoveredURL(url="https://survives.example.com", name="Survives")])
        agent = AutomaticDiscoveryAgent(page_fetcher=_FakeFetcher({
            "https://survives.example.com": PageFetchResult(status_code=200, body=_RELEVANT_BODY, final_url="https://survives.example.com"),
        }))

        with self.db.transaction() as conn:
            result = agent.run(conn, self._request(discovery_providers=["broken_test_provider", "fixed_test_provider"]))

        self.assertEqual(result.run.total_candidates, 1)
        self.assertTrue(any("broken_test_provider" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
