"""`DiscoveryService` — thin read/write orchestration over
`storage.discovery_repository`, mirroring `feedback/service.py`'s own shape:
plain functions, no business logic, only translation between this package's
domain dataclasses (`src.discovery.automatic.models`) and the storage layer's
row-shaped ones (`src.storage.models`). Deciding *when*/*what*/*why* to record
stays `AutomaticDiscoveryAgent`'s job.
"""

from __future__ import annotations

import sqlite3

from src.discovery.automatic.models import (
    DiscoveryRun,
    PlatformCandidate,
    PlatformCapabilityEstimate,
    PlatformEvidence,
    PlatformVerificationResult,
)
from src.storage import discovery_repository
from src.storage.models import (
    DiscoveryProviderObservationRecord,
    DiscoveryRunRecord,
    PlatformCandidateRecord,
    PlatformCapabilityEstimateRecord,
    PlatformDuplicateLinkRecord,
    PlatformEvidenceRecord,
    PlatformVerificationObservationRecord,
)


def record_run(conn: sqlite3.Connection, run: DiscoveryRun) -> int:
    return discovery_repository.add_run(conn, _run_to_record(run))


def update_run_summary(conn: sqlite3.Connection, run: DiscoveryRun) -> None:
    discovery_repository.update_run_summary(conn, run.run_id, _run_to_record(run))


def get_run(conn: sqlite3.Connection, run_id: str) -> DiscoveryRun | None:
    record = discovery_repository.get_run(conn, run_id)
    return _run_from_record(record) if record is not None else None


def get_run_history(conn: sqlite3.Connection) -> list[DiscoveryRun]:
    return [_run_from_record(r) for r in discovery_repository.get_run_history(conn)]


def get_latest_run(conn: sqlite3.Connection) -> DiscoveryRun | None:
    record = discovery_repository.get_latest_run(conn)
    return _run_from_record(record) if record is not None else None


def _run_to_record(run: DiscoveryRun) -> DiscoveryRunRecord:
    return DiscoveryRunRecord(
        run_id=run.run_id, request=run.request.as_dict(), started_at=run.started_at,
        providers_used=run.providers_used, completed_at=run.completed_at,
        total_candidates=run.total_candidates, new_candidate_count=run.new_candidate_count,
        duplicate_count=run.duplicate_count, verified_count=run.verified_count,
        supported_count=run.supported_count, unsupported_count=run.unsupported_count, notes=run.notes,
    )


def _run_from_record(record: DiscoveryRunRecord) -> DiscoveryRun:
    from src.discovery.automatic.models import DiscoveryRequest

    request = DiscoveryRequest(
        country=record.request.get("country"), region=record.request.get("region"),
        city=record.request.get("city"), postal_area=record.request.get("postal_area"),
        language=record.request.get("language"),
        rental_categories=record.request.get("rental_categories", []),
        property_types=record.request.get("property_types", []),
        room_or_shared_housing_intent=record.request.get("room_or_shared_housing_intent", False),
        long_or_short_term=record.request.get("long_or_short_term"),
        student_housing=record.request.get("student_housing", False),
        professional_housing=record.request.get("professional_housing", False),
        commercial_rental=record.request.get("commercial_rental", False),
        max_candidates=record.request.get("max_candidates", 50),
        allowed_domains=record.request.get("allowed_domains", []),
        excluded_domains=record.request.get("excluded_domains", []),
        minimum_confidence=record.request.get("minimum_confidence", 0.0),
        manual_urls=record.request.get("manual_urls", []),
        discovery_providers=record.request.get("discovery_providers"),
    )
    return DiscoveryRun(
        request=request, started_at=record.started_at, providers_used=record.providers_used,
        completed_at=record.completed_at, total_candidates=record.total_candidates,
        new_candidate_count=record.new_candidate_count, duplicate_count=record.duplicate_count,
        verified_count=record.verified_count, supported_count=record.supported_count,
        unsupported_count=record.unsupported_count, notes=record.notes, run_id=record.run_id, id=record.id,
    )


def record_candidate(conn: sqlite3.Connection, candidate: PlatformCandidate) -> int:
    return discovery_repository.add_candidate(conn, _candidate_to_record(candidate))


def update_candidate(conn: sqlite3.Connection, candidate: PlatformCandidate) -> None:
    discovery_repository.update_candidate(conn, _candidate_to_record(candidate))


def get_candidate(conn: sqlite3.Connection, candidate_id: str) -> PlatformCandidate | None:
    record = discovery_repository.get_candidate(conn, candidate_id)
    return _candidate_from_record(record) if record is not None else None


def get_candidate_by_domain(conn: sqlite3.Connection, normalized_domain: str) -> PlatformCandidate | None:
    record = discovery_repository.get_candidate_by_domain(conn, normalized_domain)
    return _candidate_from_record(record) if record is not None else None


def get_all_candidates(conn: sqlite3.Connection) -> list[PlatformCandidate]:
    return [_candidate_from_record(r) for r in discovery_repository.get_all_candidates(conn)]


def get_candidates_by_status(conn: sqlite3.Connection, status: str) -> list[PlatformCandidate]:
    return [_candidate_from_record(r) for r in discovery_repository.get_candidates_by_status(conn, status)]


def get_candidates_by_geography(
    conn: sqlite3.Connection, country: str | None = None, region: str | None = None, city: str | None = None,
) -> list[PlatformCandidate]:
    return [
        _candidate_from_record(r)
        for r in discovery_repository.get_candidates_by_geography(conn, country=country, region=region, city=city)
    ]


def _candidate_to_record(candidate: PlatformCandidate) -> PlatformCandidateRecord:
    return PlatformCandidateRecord(
        candidate_id=candidate.candidate_id, normalized_domain=candidate.normalized_domain,
        name=candidate.name, raw_url=candidate.raw_url, status=candidate.status.value,
        classification=candidate.classification.value, first_discovered_at=candidate.first_discovered_at,
        last_seen_at=candidate.last_seen_at, last_run_id=candidate.last_run_id, country=candidate.country,
        region=candidate.region, city=candidate.city, confidence=candidate.confidence,
        matched_platform_id=candidate.matched_platform_id, id=candidate.id,
    )


def _candidate_from_record(record: PlatformCandidateRecord) -> PlatformCandidate:
    from src.discovery.automatic.models import PlatformClassification, PlatformStatus

    return PlatformCandidate(
        candidate_id=record.candidate_id, normalized_domain=record.normalized_domain, name=record.name,
        raw_url=record.raw_url, status=PlatformStatus(record.status),
        classification=PlatformClassification(record.classification), first_discovered_at=record.first_discovered_at,
        last_seen_at=record.last_seen_at, last_run_id=record.last_run_id, country=record.country,
        region=record.region, city=record.city, confidence=record.confidence,
        matched_platform_id=record.matched_platform_id, id=record.id,
    )


def record_evidence(conn: sqlite3.Connection, evidence: PlatformEvidence) -> int:
    return discovery_repository.add_evidence(
        conn,
        PlatformEvidenceRecord(
            candidate_id=evidence.candidate_id, run_id=evidence.run_id, evidence_type=evidence.evidence_type,
            discovery_provider=evidence.discovery_provider, value=evidence.value,
            collected_at=evidence.collected_at, confidence=evidence.confidence,
        ),
    )


def get_evidence_for_candidate(conn: sqlite3.Connection, candidate_id: str) -> list[PlatformEvidence]:
    return [_evidence_from_record(r) for r in discovery_repository.get_evidence_for_candidate(conn, candidate_id)]


def get_evidence_for_run(conn: sqlite3.Connection, run_id: str) -> list[PlatformEvidence]:
    return [_evidence_from_record(r) for r in discovery_repository.get_evidence_for_run(conn, run_id)]


def _evidence_from_record(record: PlatformEvidenceRecord) -> PlatformEvidence:
    return PlatformEvidence(
        candidate_id=record.candidate_id, evidence_type=record.evidence_type,
        discovery_provider=record.discovery_provider, value=record.value, collected_at=record.collected_at,
        confidence=record.confidence, run_id=record.run_id, id=record.id,
    )


def record_verification_result(conn: sqlite3.Connection, result: PlatformVerificationResult) -> int:
    return discovery_repository.add_verification_observation(
        conn,
        PlatformVerificationObservationRecord(
            candidate_id=result.candidate_id, run_id=result.run_id, check_type=result.check_type,
            result=result.result, detail=result.detail, observed_at=result.observed_at,
        ),
    )


def get_verification_results(conn: sqlite3.Connection, candidate_id: str) -> list[PlatformVerificationResult]:
    return [
        PlatformVerificationResult(
            candidate_id=r.candidate_id, check_type=r.check_type, result=r.result, observed_at=r.observed_at,
            detail=r.detail, run_id=r.run_id, id=r.id,
        )
        for r in discovery_repository.get_verification_observations(conn, candidate_id)
    ]


def record_capability_estimate(conn: sqlite3.Connection, estimate: PlatformCapabilityEstimate) -> int:
    return discovery_repository.add_capability_estimate(
        conn,
        PlatformCapabilityEstimateRecord(
            candidate_id=estimate.candidate_id, run_id=estimate.run_id, capability_key=estimate.capability_key,
            estimated_value=estimate.estimated_value, observed_at=estimate.observed_at,
            is_estimate=estimate.is_estimate,
        ),
    )


def get_capability_estimates(conn: sqlite3.Connection, candidate_id: str) -> list[PlatformCapabilityEstimate]:
    return [
        PlatformCapabilityEstimate(
            candidate_id=r.candidate_id, capability_key=r.capability_key, estimated_value=r.estimated_value,
            observed_at=r.observed_at, is_estimate=r.is_estimate, run_id=r.run_id, id=r.id,
        )
        for r in discovery_repository.get_capability_estimates(conn, candidate_id)
    ]


def record_duplicate_link(
    conn: sqlite3.Connection, candidate_id: str, duplicate_of_candidate_id: str, matched_by: str, linked_at,
) -> int:
    return discovery_repository.add_duplicate_link(
        conn,
        PlatformDuplicateLinkRecord(
            candidate_id=candidate_id, duplicate_of_candidate_id=duplicate_of_candidate_id,
            matched_by=matched_by, linked_at=linked_at,
        ),
    )


def get_duplicate_links(conn: sqlite3.Connection, candidate_id: str) -> list[PlatformDuplicateLinkRecord]:
    return discovery_repository.get_duplicate_links(conn, candidate_id)


def record_provider_observation(
    conn: sqlite3.Connection, run_id: str, provider_id: str, succeeded: bool, observed_at,
    candidates_found: int = 0, duration_ms: int | None = None, error: str | None = None,
) -> int:
    return discovery_repository.add_provider_observation(
        conn,
        DiscoveryProviderObservationRecord(
            run_id=run_id, provider_id=provider_id, succeeded=succeeded, observed_at=observed_at,
            candidates_found=candidates_found, duration_ms=duration_ms, error=error,
        ),
    )


def get_provider_observations(conn: sqlite3.Connection, provider_id: str) -> list[DiscoveryProviderObservationRecord]:
    return discovery_repository.get_provider_observations(conn, provider_id)


def get_provider_observations_for_run(conn: sqlite3.Connection, run_id: str) -> list[DiscoveryProviderObservationRecord]:
    return discovery_repository.get_provider_observations_for_run(conn, run_id)


def get_all_provider_observations(conn: sqlite3.Connection) -> list[DiscoveryProviderObservationRecord]:
    return discovery_repository.get_all_provider_observations(conn)


def get_all_verification_observations(conn: sqlite3.Connection) -> list[PlatformVerificationObservationRecord]:
    return discovery_repository.get_all_verification_observations(conn)
