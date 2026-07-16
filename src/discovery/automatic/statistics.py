"""`compute_discovery_statistics`/`compare_discovery_runs` — computed *from*
already-stored discovery data, never inside `AutomaticDiscoveryAgent` itself.
Mirrors `geography/statistics.py`'s own "single responsibility" separation.

This is also this sprint's whole answer to the mission's "Knowledge Engine
Integration" requirement (provider effectiveness, duplicate rates, verification
success, candidate-to-supported conversion): `discovery_provider_observations`
is already an append-only per-run/per-provider ledger (migration 0008), and this
module aggregates it — the same "plain average/count/ratio over already-stored
data, no prediction, no scoring model" discipline `knowledge_service.py` already
established for connector/search performance, applied here to discovery runs
instead. A second, parallel knowledge store isn't needed.
"""

from __future__ import annotations

import sqlite3
from statistics import mean

from src.discovery.automatic import service
from src.discovery.automatic.models import DiscoveryComparison, DiscoveryStatistics, PlatformStatus


def compute_discovery_statistics(conn: sqlite3.Connection) -> DiscoveryStatistics:
    runs = service.get_run_history(conn)
    candidates = service.get_all_candidates(conn)
    verification_observations = service.get_all_verification_observations(conn)
    provider_observations = service.get_all_provider_observations(conn)

    candidates_by_status: dict[str, int] = {}
    candidates_by_classification: dict[str, int] = {}
    confidences: list[float] = []
    for candidate in candidates:
        candidates_by_status[candidate.status.value] = candidates_by_status.get(candidate.status.value, 0) + 1
        candidates_by_classification[candidate.classification.value] = (
            candidates_by_classification.get(candidate.classification.value, 0) + 1
        )
        if candidate.confidence is not None:
            confidences.append(candidate.confidence)

    provider_candidate_counts: dict[str, int] = {}
    for observation in provider_observations:
        provider_candidate_counts[observation.provider_id] = (
            provider_candidate_counts.get(observation.provider_id, 0) + observation.candidates_found
        )

    pass_fail_observations = [o for o in verification_observations if o.result in ("pass", "fail")]
    verification_pass_rate = (
        sum(1 for o in pass_fail_observations if o.result == "pass") / len(pass_fail_observations)
        if pass_fail_observations else None
    )

    total_candidates = len(candidates)
    duplicate_rate = (
        candidates_by_status.get(PlatformStatus.DUPLICATE.value, 0) / total_candidates if total_candidates else None
    )
    supported_count = candidates_by_status.get(PlatformStatus.CONNECTOR_AVAILABLE.value, 0)
    candidate_to_supported_rate = (supported_count / total_candidates) if total_candidates else None

    return DiscoveryStatistics(
        total_runs=len(runs), total_candidates=total_candidates,
        candidates_by_status=candidates_by_status, candidates_by_classification=candidates_by_classification,
        average_confidence=mean(confidences) if confidences else None,
        provider_candidate_counts=provider_candidate_counts, duplicate_rate=duplicate_rate,
        verification_pass_rate=verification_pass_rate, candidate_to_supported_rate=candidate_to_supported_rate,
    )


def compare_discovery_runs(conn: sqlite3.Connection, previous_run_id: str, current_run_id: str) -> DiscoveryComparison:
    """"Search Memory and Comparison" (the mission's own section) applied to
    platform discovery — mirrors `search_memory.models.SearchComparison`'s shape.
    Candidates are matched by `candidate_id`, which is stable across runs (see
    `agent.py`'s dedup step, which reuses an existing candidate's id rather than
    minting a new one for the same normalized domain).
    """
    previous_evidence = service.get_evidence_for_run(conn, previous_run_id)
    current_evidence = service.get_evidence_for_run(conn, current_run_id)
    previous_candidate_ids = {e.candidate_id for e in previous_evidence}
    current_candidate_ids = {e.candidate_id for e in current_evidence}

    previous_verification = {v.candidate_id: v for v in service.get_all_verification_observations(conn) if v.run_id == previous_run_id}
    current_verification = {v.candidate_id: v for v in service.get_all_verification_observations(conn) if v.run_id == current_run_id}

    all_candidates = {c.candidate_id: c for c in service.get_all_candidates(conn)}

    changed_metadata_ids = []
    changed_verification_ids = []
    changed_connector_ids = []
    for candidate_id in previous_candidate_ids & current_candidate_ids:
        candidate = all_candidates.get(candidate_id)
        if candidate is None:
            continue
        if candidate.last_run_id == current_run_id:
            changed_metadata_ids.append(candidate_id)
        if candidate_id in previous_verification and candidate_id in current_verification:
            if previous_verification[candidate_id].result != current_verification[candidate_id].result:
                changed_verification_ids.append(candidate_id)
        if candidate.status in (PlatformStatus.CONNECTOR_AVAILABLE, PlatformStatus.CONNECTOR_MISSING):
            changed_connector_ids.append(candidate_id)

    newly_supported = [
        candidate_id for candidate_id in current_candidate_ids - previous_candidate_ids
        if all_candidates.get(candidate_id) and all_candidates[candidate_id].status is PlatformStatus.CONNECTOR_AVAILABLE
    ]

    return DiscoveryComparison(
        previous_run_id=previous_run_id, current_run_id=current_run_id,
        new_candidate_ids=sorted(current_candidate_ids - previous_candidate_ids),
        removed_or_unreachable_candidate_ids=sorted(previous_candidate_ids - current_candidate_ids),
        changed_metadata_candidate_ids=sorted(set(changed_metadata_ids)),
        changed_verification_status_candidate_ids=sorted(set(changed_verification_ids)),
        changed_connector_availability_candidate_ids=sorted(set(changed_connector_ids)),
        newly_supported_locations=sorted(
            {all_candidates[cid].city for cid in newly_supported if all_candidates[cid].city}
        ),
        # PlatformCandidate stores geography (country/region/city), not rental
        # category, so this is honestly empty rather than guessed — a candidate's
        # matched rental categories live only in its PlatformEvidence rows.
        newly_supported_rental_categories=[],
    )
