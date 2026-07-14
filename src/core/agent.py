"""RentalResearchAgent — the single entry point that runs a full search end-to-end
(docs/01_System_Architecture.md "Orchestrator: the Rental Research Agent").

Owns sequencing between pipeline stages only — Discovery, Connector, Analysis, Ranking,
Report. Contains no single stage's own business logic; that stays in discovery/,
connectors/, analyzers/, ranking/, services/ respectively.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path

from src.analyzers.engine import process_listings
from src.connectors.base import Connector
from src.discovery.discovery_agent import DiscoveryAgent
from src.core.config import OUTPUT_DIR
from src.ranking.ranking_engine import RankingEngine
from src.search.search_request import SearchRequest
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
        self._ranking = RankingEngine()

    def run(self, request: SearchRequest) -> SearchRunResult:
        """Runs one search to completion: persists the request, discovers relevant
        platforms, queries each via its connector, writes every resulting listing
        through the Analysis Engine, ranks the results, persists the ranked snapshot
        (search_results), and generates the HTML report.

        A platform whose connector raises is skipped, not fatal — one broken/unreachable
        site must not discard listings other platforms did return successfully
        (resolves the open question in docs/06_Connector_Framework.md this way for V1;
        Principle 1 argues against throwing away whatever *did* succeed).
        """
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

        apartments: list[Apartment] = []
        for platform in platforms:
            try:
                connector = self._load_connector(platform.connector_module)
                raw_listings = connector.search(request.criteria)
            except Exception:
                continue

            with self._db.transaction() as conn:
                apartments.extend(process_listings(conn, raw_listings, platform.id, request.id))

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

        report_path = generate_report(self._db, request.id, output_dir=self._output_dir)

        return SearchRunResult(search_id=request.id, apartments=apartments, report_path=report_path)

    @staticmethod
    def _load_connector(connector_module: str) -> Connector:
        module = importlib.import_module(connector_module)
        try:
            connector_class = module.CONNECTOR
        except AttributeError:
            raise ImportError(
                f"{connector_module} must define CONNECTOR = <ConnectorSubclass> "
                "for the orchestrator to find it (see docs/06_Connector_Framework.md)"
            ) from None
        return connector_class()
