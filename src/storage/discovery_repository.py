"""Persistence for `discovery_runs`/`platform_candidates`/`platform_evidence`/
`platform_verification_observations`/`platform_capability_estimates`/
`platform_duplicate_links`/`discovery_provider_observations` (migration 0008,
v2.5 Step 13) — pure data access; deciding *when*/*what* to record is
`src/discovery/automatic/`'s job. Mirrors `feedback_repository.py`'s exact shape.

`platform_candidates` has one real update function (`update_candidate`) since it's
a current-state row, like `platforms` itself. Every other table here is strictly
append-only: no `update_*`/`delete_*` function exists for any of them.
"""

from __future__ import annotations

import json
import sqlite3

from src.storage.models import (
    DiscoveryProviderObservationRecord,
    DiscoveryRunRecord,
    PlatformCandidateRecord,
    PlatformCapabilityEstimateRecord,
    PlatformDuplicateLinkRecord,
    PlatformEvidenceRecord,
    PlatformVerificationObservationRecord,
)
from src.storage.models import iso, parse_iso


def add_run(conn: sqlite3.Connection, run: DiscoveryRunRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO discovery_runs
            (run_id, request_json, started_at, completed_at, providers_used_json,
             total_candidates, new_candidate_count, duplicate_count, verified_count,
             supported_count, unsupported_count, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.run_id, json.dumps(run.request), iso(run.started_at),
            iso(run.completed_at) if run.completed_at else None, json.dumps(run.providers_used),
            run.total_candidates, run.new_candidate_count, run.duplicate_count, run.verified_count,
            run.supported_count, run.unsupported_count, run.notes,
        ),
    )
    return cursor.lastrowid


def update_run_summary(conn: sqlite3.Connection, run_id: str, run: DiscoveryRunRecord) -> None:
    """The one place `discovery_runs` is updated after insertion — finalizing a
    run's own summary counters/`completed_at` once the pipeline finishes. Distinct
    from every other table here, which never updates at all.
    """
    conn.execute(
        """
        UPDATE discovery_runs SET
            completed_at = ?, total_candidates = ?, new_candidate_count = ?, duplicate_count = ?,
            verified_count = ?, supported_count = ?, unsupported_count = ?, notes = ?
        WHERE run_id = ?
        """,
        (
            iso(run.completed_at) if run.completed_at else None, run.total_candidates,
            run.new_candidate_count, run.duplicate_count, run.verified_count, run.supported_count,
            run.unsupported_count, run.notes, run_id,
        ),
    )


def get_run(conn: sqlite3.Connection, run_id: str) -> DiscoveryRunRecord | None:
    row = conn.execute("SELECT * FROM discovery_runs WHERE run_id = ?", (run_id,)).fetchone()
    return _row_to_run(row) if row is not None else None


def get_run_history(conn: sqlite3.Connection) -> list[DiscoveryRunRecord]:
    rows = conn.execute("SELECT * FROM discovery_runs ORDER BY started_at").fetchall()
    return [_row_to_run(row) for row in rows]


def get_latest_run(conn: sqlite3.Connection) -> DiscoveryRunRecord | None:
    row = conn.execute("SELECT * FROM discovery_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    return _row_to_run(row) if row is not None else None


def _row_to_run(row: sqlite3.Row) -> DiscoveryRunRecord:
    return DiscoveryRunRecord(
        id=row["id"], run_id=row["run_id"], request=json.loads(row["request_json"]),
        started_at=parse_iso(row["started_at"]),
        completed_at=parse_iso(row["completed_at"]) if row["completed_at"] else None,
        providers_used=json.loads(row["providers_used_json"]), total_candidates=row["total_candidates"],
        new_candidate_count=row["new_candidate_count"], duplicate_count=row["duplicate_count"],
        verified_count=row["verified_count"], supported_count=row["supported_count"],
        unsupported_count=row["unsupported_count"], notes=row["notes"],
    )


def add_candidate(conn: sqlite3.Connection, candidate: PlatformCandidateRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO platform_candidates
            (candidate_id, normalized_domain, name, raw_url, country, region, city, status,
             classification, confidence, matched_platform_id, first_discovered_at, last_seen_at, last_run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate.candidate_id, candidate.normalized_domain, candidate.name, candidate.raw_url,
            candidate.country, candidate.region, candidate.city, candidate.status, candidate.classification,
            candidate.confidence, candidate.matched_platform_id, iso(candidate.first_discovered_at),
            iso(candidate.last_seen_at), candidate.last_run_id,
        ),
    )
    return cursor.lastrowid


def update_candidate(conn: sqlite3.Connection, candidate: PlatformCandidateRecord) -> None:
    """Refreshes an existing candidate's current-state fields — `candidate_id`/
    `first_discovered_at` (identity/history) never change.
    """
    conn.execute(
        """
        UPDATE platform_candidates SET
            name = ?, raw_url = ?, country = ?, region = ?, city = ?, status = ?, classification = ?,
            confidence = ?, matched_platform_id = ?, last_seen_at = ?, last_run_id = ?
        WHERE candidate_id = ?
        """,
        (
            candidate.name, candidate.raw_url, candidate.country, candidate.region, candidate.city,
            candidate.status, candidate.classification, candidate.confidence, candidate.matched_platform_id,
            iso(candidate.last_seen_at), candidate.last_run_id, candidate.candidate_id,
        ),
    )


def get_candidate(conn: sqlite3.Connection, candidate_id: str) -> PlatformCandidateRecord | None:
    row = conn.execute("SELECT * FROM platform_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
    return _row_to_candidate(row) if row is not None else None


def get_candidate_by_domain(conn: sqlite3.Connection, normalized_domain: str) -> PlatformCandidateRecord | None:
    row = conn.execute(
        "SELECT * FROM platform_candidates WHERE normalized_domain = ?", (normalized_domain,),
    ).fetchone()
    return _row_to_candidate(row) if row is not None else None


def get_all_candidates(conn: sqlite3.Connection) -> list[PlatformCandidateRecord]:
    rows = conn.execute("SELECT * FROM platform_candidates ORDER BY first_discovered_at").fetchall()
    return [_row_to_candidate(row) for row in rows]


def get_candidates_by_status(conn: sqlite3.Connection, status: str) -> list[PlatformCandidateRecord]:
    rows = conn.execute(
        "SELECT * FROM platform_candidates WHERE status = ? ORDER BY first_discovered_at", (status,),
    ).fetchall()
    return [_row_to_candidate(row) for row in rows]


def get_candidates_by_geography(
    conn: sqlite3.Connection, country: str | None = None, region: str | None = None, city: str | None = None,
) -> list[PlatformCandidateRecord]:
    clauses, params = [], []
    if country is not None:
        clauses.append("country = ?")
        params.append(country)
    if region is not None:
        clauses.append("region = ?")
        params.append(region)
    if city is not None:
        clauses.append("city = ?")
        params.append(city)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM platform_candidates {where} ORDER BY first_discovered_at", params,
    ).fetchall()
    return [_row_to_candidate(row) for row in rows]


def _row_to_candidate(row: sqlite3.Row) -> PlatformCandidateRecord:
    return PlatformCandidateRecord(
        id=row["id"], candidate_id=row["candidate_id"], normalized_domain=row["normalized_domain"],
        name=row["name"], raw_url=row["raw_url"], country=row["country"], region=row["region"],
        city=row["city"], status=row["status"], classification=row["classification"],
        confidence=row["confidence"], matched_platform_id=row["matched_platform_id"],
        first_discovered_at=parse_iso(row["first_discovered_at"]), last_seen_at=parse_iso(row["last_seen_at"]),
        last_run_id=row["last_run_id"],
    )


def add_evidence(conn: sqlite3.Connection, evidence: PlatformEvidenceRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO platform_evidence
            (candidate_id, run_id, evidence_type, discovery_provider, value_json, confidence, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence.candidate_id, evidence.run_id, evidence.evidence_type, evidence.discovery_provider,
            json.dumps(evidence.value), evidence.confidence, iso(evidence.collected_at),
        ),
    )
    return cursor.lastrowid


def get_evidence_for_candidate(conn: sqlite3.Connection, candidate_id: str) -> list[PlatformEvidenceRecord]:
    rows = conn.execute(
        "SELECT * FROM platform_evidence WHERE candidate_id = ? ORDER BY collected_at", (candidate_id,),
    ).fetchall()
    return [_row_to_evidence(row) for row in rows]


def get_evidence_for_run(conn: sqlite3.Connection, run_id: str) -> list[PlatformEvidenceRecord]:
    rows = conn.execute(
        "SELECT * FROM platform_evidence WHERE run_id = ? ORDER BY collected_at", (run_id,),
    ).fetchall()
    return [_row_to_evidence(row) for row in rows]


def _row_to_evidence(row: sqlite3.Row) -> PlatformEvidenceRecord:
    return PlatformEvidenceRecord(
        id=row["id"], candidate_id=row["candidate_id"], run_id=row["run_id"], evidence_type=row["evidence_type"],
        discovery_provider=row["discovery_provider"], value=json.loads(row["value_json"]),
        confidence=row["confidence"], collected_at=parse_iso(row["collected_at"]),
    )


def add_verification_observation(conn: sqlite3.Connection, observation: PlatformVerificationObservationRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO platform_verification_observations
            (candidate_id, run_id, check_type, result, detail_json, observed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            observation.candidate_id, observation.run_id, observation.check_type, observation.result,
            json.dumps(observation.detail) if observation.detail is not None else None,
            iso(observation.observed_at),
        ),
    )
    return cursor.lastrowid


def get_verification_observations(conn: sqlite3.Connection, candidate_id: str) -> list[PlatformVerificationObservationRecord]:
    rows = conn.execute(
        "SELECT * FROM platform_verification_observations WHERE candidate_id = ? ORDER BY observed_at",
        (candidate_id,),
    ).fetchall()
    return [_row_to_verification_observation(row) for row in rows]


def get_all_verification_observations(conn: sqlite3.Connection) -> list[PlatformVerificationObservationRecord]:
    """Every verification observation ever recorded — feeds `statistics.compute_discovery_statistics()`'s
    `verification_pass_rate`.
    """
    rows = conn.execute("SELECT * FROM platform_verification_observations ORDER BY observed_at").fetchall()
    return [_row_to_verification_observation(row) for row in rows]


def _row_to_verification_observation(row: sqlite3.Row) -> PlatformVerificationObservationRecord:
    return PlatformVerificationObservationRecord(
        id=row["id"], candidate_id=row["candidate_id"], run_id=row["run_id"], check_type=row["check_type"],
        result=row["result"], detail=json.loads(row["detail_json"]) if row["detail_json"] else None,
        observed_at=parse_iso(row["observed_at"]),
    )


def add_capability_estimate(conn: sqlite3.Connection, estimate: PlatformCapabilityEstimateRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO platform_capability_estimates
            (candidate_id, run_id, capability_key, estimated_value_json, is_estimate, observed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            estimate.candidate_id, estimate.run_id, estimate.capability_key, json.dumps(estimate.estimated_value),
            int(estimate.is_estimate), iso(estimate.observed_at),
        ),
    )
    return cursor.lastrowid


def get_capability_estimates(conn: sqlite3.Connection, candidate_id: str) -> list[PlatformCapabilityEstimateRecord]:
    rows = conn.execute(
        "SELECT * FROM platform_capability_estimates WHERE candidate_id = ? ORDER BY observed_at", (candidate_id,),
    ).fetchall()
    return [
        PlatformCapabilityEstimateRecord(
            id=row["id"], candidate_id=row["candidate_id"], run_id=row["run_id"],
            capability_key=row["capability_key"], estimated_value=json.loads(row["estimated_value_json"]),
            is_estimate=bool(row["is_estimate"]), observed_at=parse_iso(row["observed_at"]),
        )
        for row in rows
    ]


def add_duplicate_link(conn: sqlite3.Connection, link: PlatformDuplicateLinkRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO platform_duplicate_links (candidate_id, duplicate_of_candidate_id, matched_by, linked_at)
        VALUES (?, ?, ?, ?)
        """,
        (link.candidate_id, link.duplicate_of_candidate_id, link.matched_by, iso(link.linked_at)),
    )
    return cursor.lastrowid


def get_duplicate_links(conn: sqlite3.Connection, candidate_id: str) -> list[PlatformDuplicateLinkRecord]:
    rows = conn.execute(
        "SELECT * FROM platform_duplicate_links WHERE candidate_id = ? ORDER BY linked_at", (candidate_id,),
    ).fetchall()
    return [
        PlatformDuplicateLinkRecord(
            id=row["id"], candidate_id=row["candidate_id"], duplicate_of_candidate_id=row["duplicate_of_candidate_id"],
            matched_by=row["matched_by"], linked_at=parse_iso(row["linked_at"]),
        )
        for row in rows
    ]


def add_provider_observation(conn: sqlite3.Connection, observation: DiscoveryProviderObservationRecord) -> int:
    cursor = conn.execute(
        """
        INSERT INTO discovery_provider_observations
            (run_id, provider_id, candidates_found, duration_ms, succeeded, error, observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation.run_id, observation.provider_id, observation.candidates_found, observation.duration_ms,
            int(observation.succeeded), observation.error, iso(observation.observed_at),
        ),
    )
    return cursor.lastrowid


def get_provider_observations(conn: sqlite3.Connection, provider_id: str) -> list[DiscoveryProviderObservationRecord]:
    rows = conn.execute(
        "SELECT * FROM discovery_provider_observations WHERE provider_id = ? ORDER BY observed_at", (provider_id,),
    ).fetchall()
    return [_row_to_provider_observation(row) for row in rows]


def get_provider_observations_for_run(conn: sqlite3.Connection, run_id: str) -> list[DiscoveryProviderObservationRecord]:
    rows = conn.execute(
        "SELECT * FROM discovery_provider_observations WHERE run_id = ? ORDER BY observed_at", (run_id,),
    ).fetchall()
    return [_row_to_provider_observation(row) for row in rows]


def get_all_provider_observations(conn: sqlite3.Connection) -> list[DiscoveryProviderObservationRecord]:
    """Every provider observation ever recorded — feeds `statistics.compute_discovery_statistics()`'s
    `provider_candidate_counts`.
    """
    rows = conn.execute("SELECT * FROM discovery_provider_observations ORDER BY observed_at").fetchall()
    return [_row_to_provider_observation(row) for row in rows]


def _row_to_provider_observation(row: sqlite3.Row) -> DiscoveryProviderObservationRecord:
    return DiscoveryProviderObservationRecord(
        id=row["id"], run_id=row["run_id"], provider_id=row["provider_id"],
        candidates_found=row["candidates_found"], duration_ms=row["duration_ms"],
        succeeded=bool(row["succeeded"]), error=row["error"], observed_at=parse_iso(row["observed_at"]),
    )
