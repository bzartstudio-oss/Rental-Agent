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
from src.knowledge import knowledge_service
from src.knowledge import metrics as knowledge_metrics
from src.ranking.ranking_engine import RankingEngine
from src.search.search_request import SearchRequest
from src.search_memory import search_memory_service
from src.services.report_generator import generate_report
from src.storage import search_repository
from src.storage.database import Database
from src.storage.models import Apartment, SearchRequestRecord, SearchResultEntry


@dataclass
class SearchRunResult:
    search_id: str
    apartments: list[Apartment]
    report_path: Path


class RentalResearchAgent:
    def __init__(self, db: Database, output_dir: Path = OUTPUT_DIR) -> None:
        self._db = db
        self._output_dir = output_dir
        self._discovery = DiscoveryAgent(db)
        self._analysis = AnalysisEngine()
        self._ranking = RankingEngine()

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

        ranked = self._ranking.rank(apartments, request)

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
            self._db, request.id, output_dir=self._output_dir, analysis_results=analysis_results
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
