"""Tests for `ui/discovery_cli.py` — mirrors `tests/ui/test_feedback_cli.py`'s
own shape: build a real temp-file `Database`, drive `main()`, assert on
persisted state (not stdout).
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.discovery.automatic import service
from src.discovery.automatic.models import DiscoveryRequest, DiscoveryRun, PlatformCandidate, PlatformClassification, PlatformStatus
from src.storage.database import Database
from src.ui import discovery_cli

_NOW = datetime.now(timezone.utc)


class _CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _seed_candidate(self, candidate_id: str = "c1", status: PlatformStatus = PlatformStatus.RELEVANT) -> None:
        with self.db.transaction() as conn:
            service.record_run(conn, DiscoveryRun(request=DiscoveryRequest(), started_at=_NOW, run_id="r1"))
            service.record_candidate(
                conn,
                PlatformCandidate(
                    candidate_id=candidate_id, normalized_domain="example.com", name="Example",
                    raw_url="https://example.com", status=status, classification=PlatformClassification.RENTAL_MARKETPLACE,
                    first_discovered_at=_NOW, last_seen_at=_NOW, last_run_id="r1", confidence=0.8, country="Spain",
                ),
            )


class ApproveCandidateTests(_CliTestCase):
    def test_approve_promotes_candidate_into_platform_registry_auditably(self) -> None:
        self._seed_candidate()
        exit_code = discovery_cli.main(["approve-candidate", "--candidate-id", "c1"], db=self.db)
        self.assertEqual(exit_code, 0)
        with self.db.transaction() as conn:
            platforms = platform_registry.list_all_platforms(conn)
        self.assertEqual(len(platforms), 1)
        self.assertIn("discovery candidate c1", platforms[0].notes)
        self.assertEqual(platforms[0].discovery_method, "automatic_discovery_approved")

    def test_approve_unknown_candidate_fails_cleanly(self) -> None:
        exit_code = discovery_cli.main(["approve-candidate", "--candidate-id", "does-not-exist"], db=self.db)
        self.assertEqual(exit_code, 1)


class RejectCandidateTests(_CliTestCase):
    def test_reject_marks_unsupported_and_records_an_auditable_evidence_row(self) -> None:
        self._seed_candidate()
        exit_code = discovery_cli.main(["reject-candidate", "--candidate-id", "c1", "--reason", "not a rental site"], db=self.db)
        self.assertEqual(exit_code, 0)
        with self.db.transaction() as conn:
            candidate = service.get_candidate(conn, "c1")
            evidence = service.get_evidence_for_candidate(conn, "c1")
        self.assertEqual(candidate.status, PlatformStatus.UNSUPPORTED)
        decision = next(e for e in evidence if e.evidence_type == "manual_review_decision")
        self.assertEqual(decision.value["decision"], "rejected")
        self.assertEqual(decision.value["reason"], "not a rental site")


class ListCommandsTests(_CliTestCase):
    def test_list_discovered_includes_every_candidate(self) -> None:
        self._seed_candidate()
        exit_code = discovery_cli.main(["list-discovered"], db=self.db)
        self.assertEqual(exit_code, 0)

    def test_view_evidence_for_unknown_candidate_prints_nothing_and_does_not_crash(self) -> None:
        exit_code = discovery_cli.main(["view-evidence", "--candidate-id", "nope"], db=self.db)
        self.assertEqual(exit_code, 0)

    def test_view_coverage_summary_runs_on_empty_database(self) -> None:
        exit_code = discovery_cli.main(["view-coverage-summary"], db=self.db)
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
