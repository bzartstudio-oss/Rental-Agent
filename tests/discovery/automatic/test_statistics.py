"""Tests for `discovery.automatic.statistics` — computed from already-stored
discovery data (this sprint's whole "Knowledge Engine Integration" answer).
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery.automatic import service, statistics
from src.discovery.automatic.models import (
    DiscoveryRequest,
    DiscoveryRun,
    PlatformCandidate,
    PlatformClassification,
    PlatformEvidence,
    PlatformStatus,
)
from src.storage.database import Database

_NOW = datetime.now(timezone.utc)


def _candidate(candidate_id: str, domain: str, status: PlatformStatus, run_id: str, confidence: float | None = 0.7) -> PlatformCandidate:
    return PlatformCandidate(
        candidate_id=candidate_id, normalized_domain=domain, name=candidate_id, raw_url=f"https://{domain}",
        status=status, classification=PlatformClassification.RENTAL_MARKETPLACE,
        first_discovered_at=_NOW, last_seen_at=_NOW, last_run_id=run_id, confidence=confidence,
    )


class ComputeDiscoveryStatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_empty_database_yields_honest_none_averages(self) -> None:
        with self.db.transaction() as conn:
            stats = statistics.compute_discovery_statistics(conn)
        self.assertEqual(stats.total_runs, 0)
        self.assertEqual(stats.total_candidates, 0)
        self.assertIsNone(stats.average_confidence)
        self.assertIsNone(stats.duplicate_rate)

    def test_aggregates_status_and_classification_counts(self) -> None:
        with self.db.transaction() as conn:
            service.record_run(conn, DiscoveryRun(request=DiscoveryRequest(), started_at=_NOW, run_id="r1"))
            service.record_candidate(conn, _candidate("c1", "a.com", PlatformStatus.CONNECTOR_AVAILABLE, "r1"))
            service.record_candidate(conn, _candidate("c2", "b.com", PlatformStatus.DUPLICATE, "r1"))
            stats = statistics.compute_discovery_statistics(conn)
        self.assertEqual(stats.total_candidates, 2)
        self.assertEqual(stats.candidates_by_status["connector_available"], 1)
        self.assertEqual(stats.candidates_by_status["duplicate"], 1)
        self.assertEqual(stats.duplicate_rate, 0.5)
        self.assertEqual(stats.candidate_to_supported_rate, 0.5)


class CompareDiscoveryRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_new_candidate_in_second_run_is_reported(self) -> None:
        with self.db.transaction() as conn:
            service.record_run(conn, DiscoveryRun(request=DiscoveryRequest(), started_at=_NOW, run_id="r1"))
            service.record_run(conn, DiscoveryRun(request=DiscoveryRequest(), started_at=_NOW, run_id="r2"))
            service.record_candidate(conn, _candidate("c1", "a.com", PlatformStatus.CONNECTOR_AVAILABLE, "r1"))
            service.record_evidence(
                conn,
                PlatformEvidence(
                    candidate_id="c1", run_id="r1", evidence_type="discovered_url", discovery_provider="test",
                    value={}, collected_at=_NOW,
                ),
            )
            service.record_candidate(conn, _candidate("c2", "b.com", PlatformStatus.RELEVANT, "r2"))
            service.record_evidence(
                conn,
                PlatformEvidence(
                    candidate_id="c2", run_id="r2", evidence_type="discovered_url", discovery_provider="test",
                    value={}, collected_at=_NOW,
                ),
            )
            comparison = statistics.compare_discovery_runs(conn, "r1", "r2")
        self.assertEqual(comparison.new_candidate_ids, ["c2"])


if __name__ == "__main__":
    unittest.main()
