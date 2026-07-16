"""`AutomaticDiscoveryAgent` — the orchestrator implementing the mission's own
12-step DISCOVERY WORKFLOW, in order: check the Existing Platform Registry,
determine whether a refresh is needed, run the selected discovery providers,
normalize domains/names, deduplicate, collect evidence, classify, verify
accessibility/relevance, estimate capabilities, calculate confidence, store
everything, and compare against previous runs. See
docs/29_Automatic_Platform_Discovery.md "Architecture"/"Discovery Workflow".

Every method takes `conn` explicitly rather than the agent owning a `Database` —
mirrors `FeedbackEngine`'s own shape, so a test can drive this against any
fixture connection.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime, timezone

from src.connectors.sdk.exceptions import ConnectorConfigurationError
from src.connectors.sdk.registry import ConnectorRegistry
from src.discovery import platform_registry
from src.discovery.automatic import capability, classification, evidence_collection, normalization, service, statistics
from src.discovery.automatic.exceptions import DiscoveryProviderError, DiscoveryValidationError
from src.discovery.automatic.factory import DiscoveryProviderFactory
from src.discovery.automatic.models import (
    DiscoveredURL,
    DiscoveryComparison,
    DiscoveryRequest,
    DiscoveryRun,
    DiscoveryStatistics,
    PlatformCandidate,
    PlatformClassification,
    PlatformDiscoveryResult,
    PlatformEvaluation,
    PlatformStatus,
)
from src.discovery.automatic.verification import HttpPageFetcher, PageFetcher, verify_domain_accessibility, verify_homepage_content
from src.storage.models import Platform

CONNECTOR_CANDIDATE_STATUSES = frozenset({PlatformStatus.CONNECTOR_AVAILABLE, PlatformStatus.CONNECTOR_MISSING})
UNSUPPORTED_STATUSES = frozenset({
    PlatformStatus.CONNECTOR_MISSING, PlatformStatus.UNSUPPORTED, PlatformStatus.IRRELEVANT,
    PlatformStatus.INACCESSIBLE, PlatformStatus.REQUIRES_LOGIN, PlatformStatus.RELEVANT, PlatformStatus.VERIFIED,
})


class AutomaticDiscoveryAgent:
    def __init__(self, page_fetcher: PageFetcher | None = None) -> None:
        self._page_fetcher = page_fetcher or HttpPageFetcher()

    # ------------------------------------------------------------------ #
    # run — the 12-step pipeline
    # ------------------------------------------------------------------ #

    def run(self, conn: sqlite3.Connection, request: DiscoveryRequest) -> PlatformDiscoveryResult:
        now = datetime.now(timezone.utc)

        # Step 2: determine whether a refresh is needed for this request's geography —
        # computed BEFORE this run's own row is recorded, so it never compares itself
        # against itself.
        should_refresh = self._should_refresh(conn, request)

        run = DiscoveryRun(request=request, started_at=now)
        service.record_run(conn, run)

        # Step 1: Existing Platform Registry — a lookup for later dedup/connector
        # matching, never a source of new candidates itself (see providers/__init__.py).
        platform_by_domain = {
            normalization.normalize_domain(platform.homepage): platform
            for platform in platform_registry.list_all_platforms(conn)
            if platform.homepage.startswith("http")
        }

        candidates_by_domain: dict[str, PlatformCandidate] = {
            candidate.normalized_domain: candidate for candidate in service.get_all_candidates(conn)
        }

        evaluations: list[tuple[PlatformEvaluation, bool]] = []
        providers_used: list[str] = []
        warnings: list[str] = []

        if should_refresh:
            # Step 3: run selected providers.
            for provider in DiscoveryProviderFactory.resolve(request.discovery_providers):
                providers_used.append(provider.provider_id)
                started = time.monotonic()
                try:
                    discovered_urls = provider.discover(request)
                except DiscoveryProviderError as exc:
                    duration_ms = int((time.monotonic() - started) * 1000)
                    service.record_provider_observation(
                        conn, run.run_id, provider.provider_id, False, now,
                        duration_ms=duration_ms, error=str(exc),
                    )
                    warnings.append(f"Provider {provider.provider_id!r} failed: {exc}")
                    continue

                duration_ms = int((time.monotonic() - started) * 1000)
                service.record_provider_observation(
                    conn, run.run_id, provider.provider_id, True, now,
                    candidates_found=len(discovered_urls), duration_ms=duration_ms,
                )

                for discovered in discovered_urls:
                    evaluation, is_new = self._evaluate_candidate(
                        conn, run, discovered, provider.provider_id, request,
                        candidates_by_domain, platform_by_domain, now,
                    )
                    evaluations.append((evaluation, is_new))
        else:
            warnings.append(
                f"Refresh policy: a discovery run for this geography completed within the last "
                f"{request.refresh_policy.max_age_days} day(s); providers were not re-run"
            )

        run.providers_used = providers_used
        run.completed_at = datetime.now(timezone.utc)
        run.total_candidates = len(candidates_by_domain)
        run.new_candidate_count = sum(1 for _, is_new in evaluations if is_new)
        run.duplicate_count = sum(1 for c in candidates_by_domain.values() if c.status is PlatformStatus.DUPLICATE)
        run.verified_count = sum(
            1 for c in candidates_by_domain.values()
            if c.status in CONNECTOR_CANDIDATE_STATUSES or c.status in (PlatformStatus.VERIFIED, PlatformStatus.RELEVANT)
        )
        run.supported_count = sum(1 for c in candidates_by_domain.values() if c.status is PlatformStatus.CONNECTOR_AVAILABLE)
        run.unsupported_count = sum(1 for c in candidates_by_domain.values() if c.status in UNSUPPORTED_STATUSES)
        run.notes = "; ".join(warnings) if warnings else None
        service.update_run_summary(conn, run)

        if evaluations:
            result_candidates = [evaluation.candidate for evaluation, _ in evaluations]
        else:
            # Refresh was skipped — still answer with whatever is already known for
            # this geography, rather than an empty, unhelpful result.
            result_candidates = service.get_candidates_by_geography(
                conn, country=request.country, region=request.region, city=request.city,
            )

        return PlatformDiscoveryResult(
            run=run,
            supported=[c for c in result_candidates if c.status is PlatformStatus.CONNECTOR_AVAILABLE],
            unsupported=[c for c in result_candidates if c.status in UNSUPPORTED_STATUSES],
            needs_review=[c for c in result_candidates if c.status is PlatformStatus.REQUIRES_MANUAL_REVIEW],
            duplicates=[c for c in result_candidates if c.status is PlatformStatus.DUPLICATE],
            warnings=warnings,
        )

    def _should_refresh(self, conn: sqlite3.Connection, request: DiscoveryRequest) -> bool:
        if request.refresh_policy.force_refresh:
            return True
        for previous_run in reversed(service.get_run_history(conn)):
            same_geography = (
                previous_run.request.country == request.country
                and previous_run.request.region == request.region
                and previous_run.request.city == request.city
            )
            if not same_geography:
                continue
            reference_time = previous_run.completed_at or previous_run.started_at
            age_seconds = (datetime.now(timezone.utc) - reference_time).total_seconds()
            return age_seconds >= request.refresh_policy.max_age_days * 86400
        return True  # no previous run for this geography — always worth running

    # ------------------------------------------------------------------ #
    # Steps 4-11 — normalize, dedup, evidence, classify, verify, estimate,
    # score, store — applied to one discovered URL at a time.
    # ------------------------------------------------------------------ #

    def _evaluate_candidate(
        self,
        conn: sqlite3.Connection,
        run: DiscoveryRun,
        discovered: DiscoveredURL,
        provider_id: str,
        request: DiscoveryRequest,
        candidates_by_domain: dict[str, PlatformCandidate],
        platform_by_domain: dict[str, Platform],
        now: datetime,
    ) -> tuple[PlatformEvaluation, bool]:
        # Step 4: normalize.
        normalized_domain = normalization.normalize_domain(discovered.url)
        existing_candidate = candidates_by_domain.get(normalized_domain)
        is_new = existing_candidate is None

        if existing_candidate is not None:
            candidate = existing_candidate
            candidate.last_seen_at = now
            candidate.last_run_id = run.run_id
        else:
            candidate = PlatformCandidate(
                candidate_id=str(uuid.uuid4()), normalized_domain=normalized_domain,
                name=discovered.name or normalized_domain, raw_url=discovered.url,
                status=PlatformStatus.DISCOVERED, classification=PlatformClassification.UNKNOWN,
                first_discovered_at=now, last_seen_at=now, last_run_id=run.run_id,
                country=request.country, region=request.region, city=request.city,
            )

        matched_platform = platform_by_domain.get(normalized_domain)
        if matched_platform is not None:
            candidate.matched_platform_id = matched_platform.id

        # Step 5: dedup — a different normalized domain that still looks like the
        # same platform by name is a genuine second row, linked rather than merged.
        duplicate_of = None
        if is_new:
            normalized_name = normalization.normalize_name(candidate.name)
            duplicate_of = normalization.find_duplicate_candidate_by_name(
                list(candidates_by_domain.values()), normalized_name, candidate.candidate_id,
            )

        fetch_result = self._page_fetcher.fetch(discovered.url)

        # Step 6: collect evidence.
        evidence = evidence_collection.collect_evidence(
            candidate.candidate_id, run.run_id, discovered, provider_id, fetch_result, request, now=now,
        )

        # Step 8: verify accessibility/relevance.
        verification_results = [
            verify_domain_accessibility(candidate.candidate_id, discovered.url, self._page_fetcher, now=now)
        ]
        verification_results += verify_homepage_content(candidate.candidate_id, fetch_result, now=now)
        for result in verification_results:
            result.run_id = run.run_id

        login_requirement = next(
            (r.result for r in verification_results if r.check_type == "login_requirement"), "unknown"
        )

        # Step 9: estimate capabilities.
        capability_estimates = capability.estimate_capabilities(
            candidate.candidate_id, fetch_result.body, login_requirement, now=now,
        )
        for estimate in capability_estimates:
            estimate.run_id = run.run_id

        # Step 7: classify.
        evidence_text = evidence_collection.evidence_text_for_classification(discovered, fetch_result)
        candidate.classification, _scores = classification.classify_candidate(evidence_text)

        # Step 10: calculate confidence.
        candidate.confidence = self._calculate_confidence(verification_results, len(evidence))

        connector_available = False
        if matched_platform is not None and matched_platform.connector_name:
            connector_available = _connector_is_available(matched_platform.connector_name)

        candidate.status, explanation = self._decide_status(
            candidate=candidate, verification_results=verification_results, duplicate_of=duplicate_of,
            connector_available=connector_available, matched_platform=matched_platform,
            minimum_confidence=request.minimum_confidence,
        )

        # Step 11: store.
        if is_new:
            service.record_candidate(conn, candidate)
        else:
            service.update_candidate(conn, candidate)
        for item in evidence:
            service.record_evidence(conn, item)
        for result in verification_results:
            service.record_verification_result(conn, result)
        for estimate in capability_estimates:
            service.record_capability_estimate(conn, estimate)
        if duplicate_of is not None:
            service.record_duplicate_link(conn, candidate.candidate_id, duplicate_of.candidate_id, "normalized_name", now)

        candidates_by_domain[normalized_domain] = candidate

        evaluation = PlatformEvaluation(
            candidate=candidate, evidence=evidence, verification=verification_results,
            capabilities=capability_estimates, explanation=explanation,
        )
        return evaluation, is_new

    def _calculate_confidence(self, verification_results, evidence_count: int) -> float:
        """Deterministic, explainable — the mean of three signals, never an ML
        score: domain reachability, content relevance, and evidence richness.
        `"unknown"`/absent checks score a neutral 0.5, never a fabricated pass.
        """

        def score(check_type: str) -> float:
            result = next((r.result for r in verification_results if r.check_type == check_type), None)
            if result == "pass":
                return 1.0
            if result == "fail":
                return 0.0
            return 0.5

        domain_score = score("domain_accessibility")
        content_score = score("listing_or_search_page_presence")
        evidence_score = min(1.0, evidence_count / 5.0)
        return round((domain_score + content_score + evidence_score) / 3, 3)

    def _decide_status(
        self, *, candidate: PlatformCandidate, verification_results, duplicate_of, connector_available: bool,
        matched_platform: Platform | None, minimum_confidence: float,
    ) -> tuple[PlatformStatus, str]:
        """First matching rule wins — a deterministic priority order, most
        specific/blocking finding first. See docs/29 "Platform Status" for the
        full rationale behind this ordering.
        """

        def result_of(check_type: str) -> str:
            return next((r.result for r in verification_results if r.check_type == check_type), "unknown")

        if duplicate_of is not None:
            return PlatformStatus.DUPLICATE, f"Same platform name as existing candidate {duplicate_of.candidate_id!r} under a different domain"

        if result_of("domain_accessibility") == "fail":
            return PlatformStatus.INACCESSIBLE, "Domain accessibility check failed"

        if result_of("login_requirement") == "login_required":
            return PlatformStatus.REQUIRES_LOGIN, "Homepage appears to require login"

        if candidate.classification is PlatformClassification.IRRELEVANT:
            return PlatformStatus.IRRELEVANT, "Classified as irrelevant to rental discovery"

        if matched_platform is not None and connector_available:
            return PlatformStatus.CONNECTOR_AVAILABLE, f"Matched existing platform {matched_platform.id!r} with a registered connector"

        if matched_platform is not None:
            return PlatformStatus.CONNECTOR_MISSING, f"Matched existing platform {matched_platform.id!r} but no connector is available"

        if candidate.confidence is None or candidate.confidence < minimum_confidence:
            return PlatformStatus.REQUIRES_MANUAL_REVIEW, f"Confidence {candidate.confidence!r} below minimum {minimum_confidence!r}"

        if candidate.classification is PlatformClassification.UNKNOWN:
            return PlatformStatus.VERIFIED, "Domain verified reachable but content did not match any known category"

        return PlatformStatus.RELEVANT, f"Classified as {candidate.classification.value} with sufficient confidence"

    # ------------------------------------------------------------------ #
    # Step 12 / mission's own exposed read methods.
    # ------------------------------------------------------------------ #

    def latest_discovery(self, conn: sqlite3.Connection) -> DiscoveryRun | None:
        return service.get_latest_run(conn)

    def discovery_history(self, conn: sqlite3.Connection) -> list[DiscoveryRun]:
        return service.get_run_history(conn)

    def compare_discovery_runs(self, conn: sqlite3.Connection, previous_run_id: str, current_run_id: str) -> DiscoveryComparison:
        return statistics.compare_discovery_runs(conn, previous_run_id, current_run_id)

    def new_platforms_since(self, conn: sqlite3.Connection, run_id: str) -> list[PlatformCandidate]:
        reference_run = service.get_run(conn, run_id)
        if reference_run is None:
            raise DiscoveryValidationError(f"Unknown discovery run {run_id!r}")
        return [c for c in service.get_all_candidates(conn) if c.first_discovered_at > reference_run.started_at]

    def platforms_needing_review(self, conn: sqlite3.Connection) -> list[PlatformCandidate]:
        return service.get_candidates_by_status(conn, PlatformStatus.REQUIRES_MANUAL_REVIEW.value)

    def platforms_missing_connectors(self, conn: sqlite3.Connection) -> list[PlatformCandidate]:
        return service.get_candidates_by_status(conn, PlatformStatus.CONNECTOR_MISSING.value)

    def coverage_summary(self, conn: sqlite3.Connection) -> DiscoveryStatistics:
        return statistics.compute_discovery_statistics(conn)


def _connector_is_available(connector_name: str) -> bool:
    """The one honest way to answer "does a certified connector exist" — reuses
    `ConnectorRegistry` exactly as `ConnectorFactory` does, rather than guessing
    from the discovered domain. Never invents availability: an unimportable
    module honestly means "no connector," not an error to propagate.
    """
    if ConnectorRegistry.is_registered(connector_name):
        return True
    try:
        ConnectorRegistry.get(connector_name)
        return True
    except ConnectorConfigurationError:
        return False
