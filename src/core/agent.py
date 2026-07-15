"""RentalResearchAgent — the single entry point that runs a full search end-to-end
(docs/01_System_Architecture.md "Orchestrator: the Rental Research Agent").

Owns sequencing between pipeline stages only — Discovery, Connector, Analysis, Ranking,
Report. Contains no single stage's own business logic; that stays in discovery/,
connectors/, analyzers/, ranking/, services/ respectively.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.analysis import analysis_service
from src.analysis.engine import AnalysisEngine
from src.analyzers.engine import process_listings
from src.connectors.sdk import ConnectorException, ConnectorFactory
from src.discovery.discovery_agent import DiscoveryAgent
from src.core.config import OUTPUT_DIR
from src.filter_engine import FilterContext, FilterEngine, FilterHistoryEntry, record_filter_execution
from src.geography import GeoContext, GeographicEngine, GeoEnrichment, compute_geo_statistics, record_geo_enrichment
from src.knowledge import knowledge_service
from src.knowledge import metrics as knowledge_metrics
from src.providers import (
    NoProviderAvailableError,
    ProviderKind,
    ProviderRegistry,
    ProviderRouter,
    build_provider_metrics,
)
from src.ranking.ranking_engine import RankingEngine
from src.search.search_request import SearchRequest
from src.search_memory import search_memory_service
from src.services.report_generator import generate_report
from src.storage import search_repository
from src.storage.database import Database
from src.storage.models import Apartment, SearchRequestRecord, SearchResultEntry
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchRunResult:
    search_id: str
    apartments: list[Apartment]
    report_path: Path


class RentalResearchAgent:
    def __init__(
        self,
        db: Database,
        output_dir: Path = OUTPUT_DIR,
        data_router: ProviderRouter | None = None,
        ai_router: ProviderRouter | None = None,
        filter_engine: FilterEngine | None = None,
        geo_engine: GeographicEngine | None = None,
    ) -> None:
        """`data_router`/`ai_router`/`filter_engine`/`geo_engine` are optional and
        default to `None` — every existing caller (every test that doesn't pass them)
        gets byte-identical behavior to before v2.0's Provider Abstraction Layer or
        v2.5's Dynamic Filter Engine/Geographic Intelligence Engine existed. See
        docs/21_Provider_Abstraction_Layer.md "Integration" for what the first two
        change when supplied; see docs/25_Dynamic_Filter_Engine.md "Integration" for
        `filter_engine`: when given, it re-filters `apartments` (with full
        `FilterContext` — a real `conn` and this run's own `analysis_results`, so
        context-dependent filters like `image_count`/`walking_distance` get real
        evidence, not just the honest "no evidence" degradation
        `search.criteria.apply_filters()` falls back to) and records `FilterHistory`,
        before `RankingEngine.rank()` runs its own (unchanged, still-called)
        `apply_filters()` pass — safe and idempotent, since `FilterEngine`'s output is
        always a subset of its input. See docs/26_Geographic_Intelligence.md
        "Integration" for `geo_engine`: when given, it enriches every (already
        filtered) apartment with a `GeoEnrichment` — never mutating the `Apartment`
        itself — and records `GeoHistory`; its output is passed straight to
        `generate_report()` alongside `analysis_results`/`ai_summary`, rather than
        wired into `AnalysisEngine`'s own scoring, per the same "diagram vs.
        implementation reconciliation" reasoning already applied to the Filter
        Engine's own integration.
        """
        self._db = db
        self._output_dir = output_dir
        self._discovery = DiscoveryAgent(db)
        self._analysis = AnalysisEngine()
        self._ranking = RankingEngine()
        self._data_router = data_router
        self._ai_router = ai_router
        self._filter_engine = filter_engine
        self._geo_engine = geo_engine

    def run(self, request: SearchRequest) -> SearchRunResult:
        """Runs one search to completion: persists the request, discovers relevant
        platforms, queries each via its connector, writes every resulting listing
        through the Analysis Engine, ranks the results, persists the ranked snapshot
        (search_results), and generates the HTML report.

        A platform whose connector raises is skipped, not fatal — one broken/unreachable
        site must not discard listings other platforms did return successfully
        (resolves the open question in docs/06_Connector_Framework.md this way for V1;
        Principle 1 argues against throwing away whatever *did* succeed). Its id and
        the raised exception are still recorded, in Search Memory's run stats (v2.0
        Step 3) and as a failed Knowledge Engine observation (v2.0 Step 4) — being
        skipped for ranking purposes isn't the same as the failure being invisible.

        Integration order (v2.0 Step 4 mission): Apartment History updates happen
        inline, per listing, inside `process_listings()`; Search Memory's completion
        record is written next; Knowledge Engine observations are recorded last,
        since `ranking_usefulness_score` needs ranking to have already happened.

        v2.0 Step 5: connectors are obtained only through `ConnectorFactory` — this
        method never imports or instantiates a connector class directly — and
        per-platform timing/success/failure now comes from the `ConnectorResult` each
        connector returns (measured once, inside `BaseConnector.search()`) rather than
        `time.perf_counter()` calls here duplicating that measurement.

        v2.0 Step 6: the Deep Analysis Engine runs once all apartments are collected,
        before ranking — the mission's own diagram shows it after Search Memory/
        Knowledge Engine, but those two already run at the very *end* of this method by
        their own explicit design (they need the final report path/apartment counts,
        see docs/17_Search_Memory.md/docs/16_Knowledge_Engine.md "Where This Runs") —
        moving them earlier would break that design and their own tests. Analysis runs
        as early as it correctly can instead: right after Apartment History, before
        Ranking, exactly matching the mission's relative ordering between those two.
        Analysis never mutates `Apartment` — its output is stored separately
        (`apartment_analysis_metrics`) and passed to the Report Generator directly.
        """
        started_at = time.perf_counter()

        with self._db.transaction() as conn:
            search_repository.insert_search_request(
                conn,
                SearchRequestRecord(
                    id=request.id,
                    created_at=request.created_at,
                    label=request.label,
                    criteria_json=request.to_criteria_json(),
                ),
            )

        platforms = self._discovery.discover(request)
        discovered_platform_ids = [platform.id for platform in platforms]
        searched_platform_ids: list[str] = []
        connector_versions: dict[str, str | None] = {}
        errors: list[str] = []
        platform_metrics: list[dict] = []

        apartments: list[Apartment] = []

        if self._data_router is not None:
            apartments.extend(
                self._run_data_router(
                    self._data_router,
                    request,
                    platforms,
                    searched_platform_ids,
                    connector_versions,
                    errors,
                    platform_metrics,
                )
            )
            # The router already covers whichever platform(s) it manages (RentCast,
            # local demo) — excluding them here prevents querying the same platform
            # twice. Any *other* registered platform (not managed by this router) is
            # untouched and still runs through the normal loop below.
            router_platform_ids = {
                provider.platform_id for provider in ProviderRegistry.all(ProviderKind.DATA)
            }
            platforms = [platform for platform in platforms if platform.id not in router_platform_ids]

        for platform in platforms:
            if not platform.connector_name:
                continue  # discover() should already filter to connector_available, but stay defensive

            try:
                connector = ConnectorFactory.get(platform)
            except ConnectorException as exc:
                errors.append(f"{platform.id}: {exc}")
                platform_metrics.append(
                    {
                        "platform_id": platform.id,
                        "results_count": 0,
                        "failed": True,
                        "response_time_ms": None,
                        "raw_listings": None,
                        "parsing_success": False,
                    }
                )
                continue

            result = connector.search(request)

            if not result.success:
                errors.append(f"{platform.id}: {result.error}")
                platform_metrics.append(
                    {
                        "platform_id": platform.id,
                        "results_count": 0,
                        "failed": True,
                        "response_time_ms": result.response_time_ms,
                        "raw_listings": None,
                        "parsing_success": False,
                    }
                )
                continue

            searched_platform_ids.append(platform.id)
            connector_versions[platform.id] = platform.connector_version
            platform_metrics.append(
                {
                    "platform_id": platform.id,
                    "results_count": result.results_count,
                    "failed": False,
                    "response_time_ms": result.response_time_ms,
                    "raw_listings": result.listings,
                    "parsing_success": True,
                }
            )

            with self._db.transaction() as conn:
                apartments.extend(process_listings(conn, result.listings, platform.id, request.id))

        with self._db.transaction() as conn:
            analysis_results = self._analysis.analyze(
                conn, apartments, location=request.location, search_id=request.id
            )
            for result in analysis_results.values():
                analysis_service.record_analysis(conn, result)

        if self._filter_engine is not None:
            apartments = self._run_filter_engine(request, apartments, analysis_results)

        geo_enrichments: dict[str, GeoEnrichment] | None = None
        if self._geo_engine is not None:
            geo_enrichments = self._run_geo_engine(request, apartments)

        ranked = self._ranking.rank(apartments, request)

        ai_summary: str | None = None
        if self._ai_router is not None:
            try:
                ai_outcome = self._ai_router.run_with_fallback(lambda provider: provider.summarize(ranked, request))
                ai_summary = ai_outcome.result
            except NoProviderAvailableError as exc:
                errors.append(f"ai_provider_router: {exc}")

        with self._db.transaction() as conn:
            for entry in ranked:
                search_repository.add_search_result(
                    conn,
                    SearchResultEntry(
                        search_id=request.id,
                        apartment_id=entry.apartment.id,
                        rank=entry.rank,
                        score=entry.score,
                        score_breakdown_json=json.dumps(entry.score_breakdown),
                        price_at_search=entry.apartment.current_price,
                        status_at_search=entry.apartment.current_status,
                    ),
                )

        report_path = generate_report(
            self._db,
            request.id,
            output_dir=self._output_dir,
            analysis_results=analysis_results,
            ai_summary=ai_summary,
            geo_enrichments=geo_enrichments,
        )
        execution_time_ms = int((time.perf_counter() - started_at) * 1000)

        with self._db.transaction() as conn:
            search_memory_service.record_completed_search(
                conn,
                request,
                execution_time_ms=execution_time_ms,
                discovered_platform_ids=discovered_platform_ids,
                searched_platform_ids=searched_platform_ids,
                connector_versions=connector_versions,
                errors=errors,
                apartment_count=len(apartments),
                report_path=str(report_path),
            )

        with self._db.transaction() as conn:
            for entry in platform_metrics:
                ranking_score = (
                    knowledge_metrics.ranking_usefulness_score(entry["platform_id"], ranked, apartments)
                    if not entry["failed"]
                    else None
                )
                knowledge_service.record_platform_observation(
                    conn,
                    entry["platform_id"],
                    request.id,
                    results_count=entry["results_count"],
                    failed=entry["failed"],
                    response_time_ms=entry["response_time_ms"],
                    raw_listings=entry["raw_listings"],
                    ranking_usefulness_score=ranking_score,
                    parsing_success=entry["parsing_success"],
                    observed_at=datetime.now(timezone.utc),
                )

        return SearchRunResult(search_id=request.id, apartments=apartments, report_path=report_path)

    def _run_data_router(
        self,
        data_router: ProviderRouter,
        request: SearchRequest,
        discovered_platforms: list,
        searched_platform_ids: list[str],
        connector_versions: dict[str, str | None],
        errors: list[str],
        platform_metrics: list[dict],
    ) -> list[Apartment]:
        """Runs `data_router.run_with_fallback()` once and records exactly the same
        bookkeeping (`searched_platform_ids`/`connector_versions`/`platform_metrics`/
        `errors`) a normal per-platform loop iteration would — attributed to the
        resolved provider's real `platform_id` — so Search Memory/Knowledge Engine
        can't tell the difference between a router-selected platform and a directly-
        queried one. See docs/21_Provider_Abstraction_Layer.md "Integration".
        """
        try:
            outcome = data_router.run_with_fallback(
                lambda provider: provider.search(request),
                is_success=lambda result: result.success,
            )
        except NoProviderAvailableError as exc:
            errors.append(f"data_provider_router: {exc}")
            platform_metrics.append(
                {
                    "platform_id": "data_provider_router",
                    "results_count": 0,
                    "failed": True,
                    "response_time_ms": None,
                    "raw_listings": None,
                    "parsing_success": False,
                }
            )
            return []

        provider = ProviderRegistry.get(outcome.provider_id)
        platform_id = provider.platform_id
        result = outcome.result

        # Structured logging + metrics collection (v2.5 Step 8, docs/24_Production_Providers.md
        # "Metrics") — built here for visibility into *this* run; NOT written to the
        # Knowledge Engine from this point (that would double-write it) — the existing
        # `platform_metrics`/`knowledge_service.record_platform_observation` loop at the
        # end of `run()` already covers this same platform_id, below.
        run_metrics = build_provider_metrics(outcome.provider_id, platform_id, result)
        logger.info(
            "provider run metrics",
            extra={
                "provider_id": run_metrics.provider_id,
                "platform_id": run_metrics.platform_id,
                "execution_time_ms": run_metrics.execution_time_ms,
                "success": run_metrics.success,
                "listing_count": run_metrics.listing_count,
                "duplicate_rate": run_metrics.duplicate_rate,
                "extraction_quality_score": run_metrics.extraction_quality_score,
                "image_quality_score": run_metrics.image_quality_score,
                "availability_quality_score": run_metrics.availability_quality_score,
            },
        )

        registered = next((p for p in discovered_platforms if p.id == platform_id), None)
        if registered is None:
            # The router resolved a real, available data provider, but its underlying
            # platform has no row in `platforms` yet (e.g. discovery sync never ran) —
            # `apartments.platform_id` has a real foreign key to `platforms(id)`, so
            # writing listings now would fail with an integrity error, not a graceful
            # ConnectorResult failure. Reported the same honest way any other
            # misconfiguration is: an error entry, zero apartments, never a crash.
            errors.append(
                f"data_provider_router: resolved platform {platform_id!r} is not registered "
                "in `platforms` — run platform discovery sync first"
            )
            platform_metrics.append(
                {
                    "platform_id": platform_id,
                    "results_count": 0,
                    "failed": True,
                    "response_time_ms": result.response_time_ms,
                    "raw_listings": None,
                    "parsing_success": False,
                }
            )
            return []

        searched_platform_ids.append(platform_id)
        connector_versions[platform_id] = registered.connector_version
        platform_metrics.append(
            {
                "platform_id": platform_id,
                "results_count": result.results_count,
                "failed": False,
                "response_time_ms": result.response_time_ms,
                "raw_listings": result.listings,
                "parsing_success": True,
            }
        )

        with self._db.transaction() as conn:
            return process_listings(conn, result.listings, platform_id, request.id)

    def _run_filter_engine(
        self,
        request: SearchRequest,
        apartments: list[Apartment],
        analysis_results: dict,
    ) -> list[Apartment]:
        """Runs `self._filter_engine` over every collected apartment, with a real
        `FilterContext` (this run's own `conn`/`analysis_results`, not the empty one
        `search.criteria.get_filter()`'s fallback uses) so context-dependent filters
        (`image_count`, `walking_distance`, `public_transport_time`,
        `maximum_distance`) actually see evidence. Records `FilterHistory` — search
        id, filter set, execution time, results count, statistics — via the same
        `filter_execution_history` table (migration 0005) `docs/25_Dynamic_Filter_Engine.md`
        describes. See docs/25 "Integration" for why this runs *before*
        `RankingEngine.rank()` rather than replacing its own `apply_filters()` call.
        """
        now = datetime.now(timezone.utc)
        with self._db.transaction() as conn:
            context = FilterContext(conn=conn, analysis_results=analysis_results)
            results, statistics = self._filter_engine.run(apartments, request.criteria, context)
            matched_ids = {result.apartment_id for result in results if result.matches}
            filtered = [apartment for apartment in apartments if apartment.id in matched_ids]

            record_filter_execution(
                conn,
                FilterHistoryEntry(
                    search_id=request.id,
                    filter_set=request.criteria,
                    total_apartments=statistics.total_apartments,
                    matched_count=statistics.matched_count,
                    statistics=statistics,
                    recorded_at=now,
                    execution_time_ms=statistics.execution_time_ms,
                ),
            )

        logger.info(
            "filter engine run",
            extra={
                "search_id": request.id,
                "total_apartments": statistics.total_apartments,
                "matched_count": statistics.matched_count,
                "match_rate": statistics.match_rate,
                "execution_time_ms": statistics.execution_time_ms,
            },
        )
        return filtered

    def _run_geo_engine(
        self,
        request: SearchRequest,
        apartments: list[Apartment],
    ) -> dict[str, GeoEnrichment]:
        """Runs `self._geo_engine` over every (already filtered) apartment, with a
        real `GeoContext` (this run's own `conn`/`request.location`), and records one
        `GeoHistory` row per apartment via `geo_enrichment_history` (migration 0006).
        Never mutates any `Apartment` — see `GeographicEngine.enrich()`'s own
        docstring — its output is an independent dict handed to `generate_report()`.
        See docs/26_Geographic_Intelligence.md "Integration".
        """
        now = datetime.now(timezone.utc)
        with self._db.transaction() as conn:
            context = GeoContext(conn=conn, location=request.location)
            enrichments = self._geo_engine.enrich_many(apartments, context)
            statistics = compute_geo_statistics(enrichments)

            for enrichment in enrichments.values():
                record_geo_enrichment(conn, enrichment, recorded_at=now, search_id=request.id)

        logger.info(
            "geo engine run",
            extra={
                "search_id": request.id,
                "total_apartments": statistics.total_apartments,
                "enriched_count": statistics.enriched_count,
                "coverage_rate": statistics.coverage_rate,
            },
        )
        return enrichments
