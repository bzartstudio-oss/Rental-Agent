"""Phase 2 exit-criteria test (docs/10_Roadmap.md), extended for the v1.1 Multi-Platform
Discovery Framework (docs/05_Platform_Discovery.md): DiscoveryAgent.discover(request)
returns only connector-available platforms, and sync_platforms() implements all five
required behaviors — load existing, detect duplicates, update metadata, save new
platforms, and mark unsupported ones.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.discovery.discovery_agent import DiscoveryAgent, PlatformCandidate
from src.storage.database import Database
from src.storage.models import Platform


class DiscoveryAgentSearchFacingTests(unittest.TestCase):
    """discover() — the method core/agent.py calls for every real search."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.agent = DiscoveryAgent(self.db)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _register(self, id_: str, connector_available: bool) -> None:
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn,
                Platform(
                    id=id_,
                    name=id_,
                    country="Testland",
                    homepage=f"https://{id_}.example.com",
                    connector_available=connector_available,
                    connector_name=id_ if connector_available else None,
                    created_at=datetime.now(timezone.utc),
                ),
            )

    def test_discover_returns_a_connector_available_platform(self) -> None:
        self._register("seed_platform", connector_available=True)

        results = self.agent.discover(request=None)

        self.assertEqual([p.id for p in results], ["seed_platform"])

    def test_discover_excludes_platforms_without_a_connector(self) -> None:
        self._register("available_platform", connector_available=True)
        self._register("unsupported_platform", connector_available=False)

        results = self.agent.discover(request=None)

        self.assertEqual([p.id for p in results], ["available_platform"])

    def test_discover_returns_empty_list_when_no_platforms_registered(self) -> None:
        results = self.agent.discover(request=None)
        self.assertEqual(results, [])


class DiscoveryAgentSyncTests(unittest.TestCase):
    """sync_platforms() — the five required discovery-framework behaviors."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.agent = DiscoveryAgent(self.db)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_saves_newly_discovered_platforms(self) -> None:
        candidate = PlatformCandidate(
            platform_id="new_platform",
            name="New Platform",
            country="Testland",
            homepage="https://new-platform.example.com",
            connector_available=False,
            discovery_method="manual_research",
        )

        report = self.agent.sync_platforms([candidate])

        self.assertEqual(report.new_platforms, ["new_platform"])
        self.assertEqual(report.updated_platforms, [])

        with self.db.transaction() as conn:
            fetched = platform_registry.get_platform(conn, "new_platform")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "New Platform")

    def test_marks_unsupported_platforms_for_future_connector_development(self) -> None:
        candidate = PlatformCandidate(
            platform_id="no_connector_yet",
            name="No Connector Yet",
            country="Testland",
            homepage="https://no-connector-yet.example.com",
            connector_available=False,
            discovery_method="manual_research",
        )

        report = self.agent.sync_platforms([candidate])

        self.assertEqual(report.marked_unsupported, ["no_connector_yet"])

        with self.db.transaction() as conn:
            fetched = platform_registry.get_platform(conn, "no_connector_yet")
        self.assertIsNotNone(fetched)  # stays in the registry — known, just unsupported
        self.assertFalse(fetched.connector_available)

    def test_detects_duplicate_by_exact_platform_id(self) -> None:
        original = PlatformCandidate(
            platform_id="dup_platform", name="Original Name", country="Testland",
            homepage="https://dup.example.com",
        )
        self.agent.sync_platforms([original])

        again = PlatformCandidate(
            platform_id="dup_platform", name="Updated Name", country="Testland",
            homepage="https://dup.example.com",
        )
        report = self.agent.sync_platforms([again])

        self.assertEqual(report.new_platforms, [])
        self.assertEqual(report.updated_platforms, ["dup_platform"])

        with self.db.transaction() as conn:
            all_platforms = platform_registry.list_all_platforms(conn)
        self.assertEqual(len(all_platforms), 1)  # not duplicated
        self.assertEqual(all_platforms[0].name, "Updated Name")

    def test_detects_duplicate_by_normalized_homepage_even_with_different_id(self) -> None:
        original = PlatformCandidate(
            platform_id="platform_v1", name="Platform", country="Testland",
            homepage="https://www.sameplatform.example.com/",
        )
        self.agent.sync_platforms([original])

        # A re-discovery of the same real-world platform under a different candidate id,
        # e.g. re-run with a slightly different slugging convention.
        rediscovered = PlatformCandidate(
            platform_id="platform_v2", name="Platform (rediscovered)", country="Testland",
            homepage="http://sameplatform.example.com",  # no www, different scheme, no trailing slash
        )
        report = self.agent.sync_platforms([rediscovered])

        self.assertEqual(report.new_platforms, [])
        self.assertEqual(report.updated_platforms, ["platform_v1"])  # updates the ORIGINAL id
        self.assertEqual(report.duplicate_candidate_ids, ["platform_v2"])

        with self.db.transaction() as conn:
            all_platforms = platform_registry.list_all_platforms(conn)
        self.assertEqual(len(all_platforms), 1)

    def test_updates_metadata_and_bumps_last_verified_on_duplicate(self) -> None:
        original = PlatformCandidate(
            platform_id="refresh_me", name="Old Name", country="Testland",
            homepage="https://refresh-me.example.com", supported_cities=["City A"],
        )
        self.agent.sync_platforms([original])

        with self.db.transaction() as conn:
            before = platform_registry.get_platform(conn, "refresh_me")
        # last_verified means "recorded by a sync," not "live-checked" (see
        # discovery/known_platforms.py) — so even the first save sets it.
        self.assertIsNotNone(before.last_verified)

        refreshed = PlatformCandidate(
            platform_id="refresh_me", name="New Name", country="Testland",
            homepage="https://refresh-me.example.com", supported_cities=["City A", "City B"],
        )
        self.agent.sync_platforms([refreshed])

        with self.db.transaction() as conn:
            after = platform_registry.get_platform(conn, "refresh_me")

        self.assertEqual(after.name, "New Name")
        self.assertEqual(after.supported_cities, ["City A", "City B"])
        self.assertGreaterEqual(after.last_verified, before.last_verified)  # bumped, not stale

    def test_loads_existing_platforms_so_a_batch_can_dedupe_against_earlier_syncs(self) -> None:
        self.agent.sync_platforms(
            [PlatformCandidate(platform_id="p1", name="P1", country="Testland", homepage="https://p1.example.com")]
        )

        loaded = self.agent.load_platforms()  # behavior 1, exercised directly

        self.assertEqual([p.id for p in loaded], ["p1"])

    def test_a_batch_can_dedupe_against_earlier_candidates_in_the_same_batch(self) -> None:
        same_homepage_twice = [
            PlatformCandidate(
                platform_id="batch_a", name="Batch A", country="Testland",
                homepage="https://batch-dup.example.com",
            ),
            PlatformCandidate(
                platform_id="batch_b", name="Batch B (same real platform)", country="Testland",
                homepage="https://batch-dup.example.com",
            ),
        ]

        report = self.agent.sync_platforms(same_homepage_twice)

        self.assertEqual(report.new_platforms, ["batch_a"])
        self.assertEqual(report.updated_platforms, ["batch_a"])
        self.assertEqual(report.duplicate_candidate_ids, ["batch_b"])

        with self.db.transaction() as conn:
            all_platforms = platform_registry.list_all_platforms(conn)
        self.assertEqual(len(all_platforms), 1)


if __name__ == "__main__":
    unittest.main()
