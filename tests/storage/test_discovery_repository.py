"""Migration + round-trip tests for `storage/discovery_repository.py` +
migration 0008's seven tables (v2.5 Step 13) — real database, real round-trips.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.storage import discovery_repository
from src.storage.database import Database
from src.storage.models import (
    DiscoveryProviderObservationRecord,
    DiscoveryRunRecord,
    PlatformCandidateRecord,
    PlatformCapabilityEstimateRecord,
    PlatformDuplicateLinkRecord,
    PlatformEvidenceRecord,
    PlatformVerificationObservationRecord,
)

_NOW = datetime.now(timezone.utc)


class MigrationTests(unittest.TestCase):
    def test_all_seven_tables_exist_after_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Database(db_path=Path(tmp_dir) / "test.db")
            with db.transaction() as conn:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in (
                "discovery_runs", "platform_candidates", "platform_evidence",
                "platform_verification_observations", "platform_capability_estimates",
                "platform_duplicate_links", "discovery_provider_observations",
            ):
                self.assertIn(table, tables)


class _DbTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()


class DiscoveryRunRepositoryTests(_DbTestCase):
    def test_add_and_get_run(self) -> None:
        run = DiscoveryRunRecord(
            run_id="r1", request={"country": "Spain"}, started_at=_NOW, providers_used=["curated_seed"],
        )
        with self.db.transaction() as conn:
            discovery_repository.add_run(conn, run)
            fetched = discovery_repository.get_run(conn, "r1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.request, {"country": "Spain"})
        self.assertEqual(fetched.providers_used, ["curated_seed"])

    def test_update_run_summary_is_the_only_mutation(self) -> None:
        run = DiscoveryRunRecord(run_id="r1", request={}, started_at=_NOW, providers_used=[])
        with self.db.transaction() as conn:
            discovery_repository.add_run(conn, run)
            run.completed_at = _NOW
            run.total_candidates = 5
            discovery_repository.update_run_summary(conn, "r1", run)
            fetched = discovery_repository.get_run(conn, "r1")
        self.assertEqual(fetched.total_candidates, 5)
        self.assertIsNotNone(fetched.completed_at)

    def test_get_run_history_and_latest(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_run(conn, DiscoveryRunRecord(run_id="r1", request={}, started_at=_NOW, providers_used=[]))
            discovery_repository.add_run(conn, DiscoveryRunRecord(run_id="r2", request={}, started_at=_NOW, providers_used=[]))
            history = discovery_repository.get_run_history(conn)
            latest = discovery_repository.get_latest_run(conn)
        self.assertEqual([r.run_id for r in history], ["r1", "r2"])
        self.assertEqual(latest.run_id, "r2")


class PlatformCandidateRepositoryTests(_DbTestCase):
    """`platform_candidates.last_run_id` is `NOT NULL REFERENCES discovery_runs(run_id)`
    — `setUp` seeds run "r1" so every candidate insert here has somewhere real to
    point at.
    """

    def setUp(self) -> None:
        super().setUp()
        with self.db.transaction() as conn:
            discovery_repository.add_run(conn, DiscoveryRunRecord(run_id="r1", request={}, started_at=_NOW, providers_used=[]))

    def _candidate(self, **overrides) -> PlatformCandidateRecord:
        defaults = dict(
            candidate_id="c1", normalized_domain="example.com", name="Example", raw_url="https://example.com",
            status="discovered", classification="unknown", first_discovered_at=_NOW, last_seen_at=_NOW,
            last_run_id="r1",
        )
        defaults.update(overrides)
        return PlatformCandidateRecord(**defaults)

    def test_add_and_get_candidate(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_candidate(conn, self._candidate())
            fetched = discovery_repository.get_candidate(conn, "c1")
            by_domain = discovery_repository.get_candidate_by_domain(conn, "example.com")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Example")
        self.assertEqual(by_domain.candidate_id, "c1")

    def test_update_candidate_preserves_identity_and_history(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_candidate(conn, self._candidate())
            updated = self._candidate(status="relevant", confidence=0.8)
            discovery_repository.update_candidate(conn, updated)
            fetched = discovery_repository.get_candidate(conn, "c1")
        self.assertEqual(fetched.status, "relevant")
        self.assertEqual(fetched.confidence, 0.8)
        self.assertEqual(fetched.first_discovered_at, _NOW)

    def test_get_candidates_by_status_and_geography(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_candidate(conn, self._candidate(candidate_id="c1", country="Spain", city="Valencia"))
            discovery_repository.add_candidate(
                conn, self._candidate(candidate_id="c2", normalized_domain="other.com", country="France", status="relevant"),
            )
            by_status = discovery_repository.get_candidates_by_status(conn, "relevant")
            by_geo = discovery_repository.get_candidates_by_geography(conn, country="Spain")
        self.assertEqual([c.candidate_id for c in by_status], ["c2"])
        self.assertEqual([c.candidate_id for c in by_geo], ["c1"])


class AppendOnlyTableTests(_DbTestCase):
    """Confirms `platform_evidence`/`platform_verification_observations`/
    `platform_capability_estimates`/`platform_duplicate_links`/
    `discovery_provider_observations` have no update/delete function anywhere —
    "Never overwrite evidence" (the mission's own words). `setUp` seeds run "r1"
    and candidates "c1"/"c2" so every append-only insert has somewhere real to
    point its foreign keys at.
    """

    def setUp(self) -> None:
        super().setUp()
        with self.db.transaction() as conn:
            discovery_repository.add_run(conn, DiscoveryRunRecord(run_id="r1", request={}, started_at=_NOW, providers_used=[]))
            for candidate_id, domain in (("c1", "example.com"), ("c2", "other.com")):
                discovery_repository.add_candidate(
                    conn,
                    PlatformCandidateRecord(
                        candidate_id=candidate_id, normalized_domain=domain, name=candidate_id, raw_url=f"https://{domain}",
                        status="discovered", classification="unknown", first_discovered_at=_NOW, last_seen_at=_NOW,
                        last_run_id="r1",
                    ),
                )

    def test_repository_module_exposes_no_mutation_for_append_only_tables(self) -> None:
        module_functions = {name for name in dir(discovery_repository) if not name.startswith("_")}
        for forbidden in (
            "update_evidence", "delete_evidence", "update_verification_observation",
            "delete_verification_observation", "update_capability_estimate", "delete_capability_estimate",
            "update_duplicate_link", "delete_duplicate_link", "update_provider_observation",
            "delete_provider_observation",
        ):
            self.assertNotIn(forbidden, module_functions)

    def test_evidence_round_trip_and_repeated_collection_appends(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_evidence(
                conn,
                PlatformEvidenceRecord(
                    candidate_id="c1", run_id="r1", evidence_type="discovered_url", discovery_provider="curated_seed",
                    value={"url": "https://example.com"}, collected_at=_NOW,
                ),
            )
            discovery_repository.add_evidence(
                conn,
                PlatformEvidenceRecord(
                    candidate_id="c1", run_id="r1", evidence_type="discovered_url", discovery_provider="curated_seed",
                    value={"url": "https://example.com"}, collected_at=_NOW,
                ),
            )
            all_evidence = discovery_repository.get_evidence_for_candidate(conn, "c1")
            for_run = discovery_repository.get_evidence_for_run(conn, "r1")
        self.assertEqual(len(all_evidence), 2)  # both rows kept, never merged/overwritten
        self.assertEqual(len(for_run), 2)

    def test_verification_observation_round_trip(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_verification_observation(
                conn,
                PlatformVerificationObservationRecord(
                    candidate_id="c1", run_id="r1", check_type="domain_accessibility", result="fail",
                    observed_at=_NOW, detail={"error": "timeout"},
                ),
            )
            observations = discovery_repository.get_verification_observations(conn, "c1")
            all_observations = discovery_repository.get_all_verification_observations(conn)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].result, "fail")
        self.assertEqual(len(all_observations), 1)

    def test_capability_estimate_round_trip_always_marked_as_estimate(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_capability_estimate(
                conn,
                PlatformCapabilityEstimateRecord(
                    candidate_id="c1", run_id="r1", capability_key="images", estimated_value={"present": True},
                    observed_at=_NOW,
                ),
            )
            estimates = discovery_repository.get_capability_estimates(conn, "c1")
        self.assertTrue(estimates[0].is_estimate)

    def test_duplicate_link_round_trip(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_duplicate_link(
                conn, PlatformDuplicateLinkRecord(candidate_id="c2", duplicate_of_candidate_id="c1", matched_by="normalized_name", linked_at=_NOW),
            )
            links = discovery_repository.get_duplicate_links(conn, "c2")
        self.assertEqual(links[0].duplicate_of_candidate_id, "c1")

    def test_provider_observation_round_trip(self) -> None:
        with self.db.transaction() as conn:
            discovery_repository.add_provider_observation(
                conn,
                DiscoveryProviderObservationRecord(
                    run_id="r1", provider_id="curated_seed", succeeded=True, observed_at=_NOW, candidates_found=3,
                ),
            )
            for_provider = discovery_repository.get_provider_observations(conn, "curated_seed")
            for_run = discovery_repository.get_provider_observations_for_run(conn, "r1")
            everything = discovery_repository.get_all_provider_observations(conn)
        self.assertEqual(len(for_provider), 1)
        self.assertEqual(len(for_run), 1)
        self.assertEqual(len(everything), 1)


if __name__ == "__main__":
    unittest.main()
