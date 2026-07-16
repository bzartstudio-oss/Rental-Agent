"""V1 entry point — the only place a human interacts with the system directly
(docs/02_Folder_Guide.md). Thin: parses arguments, builds a SearchRequest, runs it
through RentalResearchAgent, prints where the report landed. All real logic lives in
core/agent.py and below — this module must not contain business logic itself.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.core.agent import RentalResearchAgent
from src.core.config import OUTPUT_DIR
from src.discovery.discovery_agent import DiscoveryAgent
from src.discovery.known_platforms import ALL_KNOWN_PLATFORMS
from src.feedback import FeedbackEngine, FeedbackMode
from src.filter_engine import FilterEngine
from src.geography import GeographicEngine
from src.providers import ProviderKind, ProviderRouter
from src.ranking_v2 import COMPREHENSIVE_PROFILE, DEFAULT_PROFILE, RankingEngineV2
from src.search.search_request import SearchRequest
from src.storage.database import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rental-agent", description="Rental Intelligence Platform search")
    parser.add_argument("--location", required=True, help="Where to search, e.g. 'Example City'")
    parser.add_argument("--max-price", type=float, default=None)
    parser.add_argument("--min-bedrooms", type=float, default=None)
    parser.add_argument("--min-bathrooms", type=float, default=None)
    parser.add_argument("--min-sqft", type=float, default=None)
    parser.add_argument("--label", default=None, help="Optional name for this search")
    parser.add_argument(
        "--use-provider-router",
        action="store_true",
        help=(
            "Route data (RentCast / local demo) and AI (Ollama / no-op) selection "
            "through the Provider Abstraction Layer instead of querying every "
            "registered platform directly — see docs/21_Provider_Abstraction_Layer.md. "
            "Off by default; the default flow is unchanged."
        ),
    )
    parser.add_argument(
        "--use-filter-engine",
        action="store_true",
        help=(
            "Re-filter results through the Dynamic Filter Engine (39 built-in filters, "
            "full FilterStatistics/FilterHistory) instead of relying only on "
            "RankingEngine's own hard-filter pass — see docs/25_Dynamic_Filter_Engine.md. "
            "Off by default; the default flow is unchanged."
        ),
    )
    parser.add_argument(
        "--use-geo-engine",
        action="store_true",
        help=(
            "Enrich results with the Geographic Intelligence Engine (distances, "
            "estimated travel times, nearby services) and display them in the report "
            "— see docs/26_Geographic_Intelligence.md. Off by default; the default "
            "flow is unchanged."
        ),
    )
    parser.add_argument(
        "--use-ranking-v2",
        action="store_true",
        help=(
            "Re-score results through the Intelligent Ranking Engine V2 (explainable, "
            "evidence-based, user-configurable weights) and display Score/Confidence/"
            "Top Factors in the report — see docs/27_Intelligent_Ranking_Engine.md. "
            "Off by default; the default flow is unchanged."
        ),
    )
    parser.add_argument(
        "--ranking-profile",
        choices=("default", "comprehensive"),
        default="default",
        help=(
            "Which built-in RankingProfile to use with --use-ranking-v2: 'default' "
            "is the mission's own worked example (Price 40%%, Walking Distance 25%%, "
            "Availability 15%%, Public Transport 10%%, Lifestyle 10%%); 'comprehensive' "
            "weights every registered rule equally. Ignored without --use-ranking-v2."
        ),
    )
    parser.add_argument(
        "--feedback-profile-id",
        default=None,
        help=(
            "Enable the User Feedback and Preference Learning Engine for this run under "
            "the given profile id — records active filters as feedback and (with "
            "--use-ranking-v2) resolves the ranking profile through the learned "
            "preferences per --feedback-mode. See "
            "docs/28_User_Feedback_and_Preference_Learning.md. Off by default."
        ),
    )
    parser.add_argument(
        "--feedback-mode",
        choices=[m.value for m in FeedbackMode],
        default=FeedbackMode.SUGGESTED.value,
        help=(
            "explicit_only: ignore learned preferences entirely. suggested (default): "
            "compute them but never apply automatically. assisted: apply learned "
            "adjustments to ranking weights, recording every one. Ignored without "
            "--feedback-profile-id."
        ),
    )
    return parser


def main(argv: list[str] | None = None, db: Database | None = None, output_dir: Path = OUTPUT_DIR) -> int:
    """`db` and `output_dir` default to the real project database/output folder — the
    parameters exist so tests can point the CLI at a temporary database instead of
    writing into real project data on every test run.
    """
    args = build_parser().parse_args(argv)

    criteria = {}
    if args.max_price is not None:
        criteria["max_price"] = args.max_price
    if args.min_bedrooms is not None:
        criteria["min_bedrooms"] = args.min_bedrooms
    if args.min_bathrooms is not None:
        criteria["min_bathrooms"] = args.min_bathrooms
    if args.min_sqft is not None:
        criteria["min_sqft"] = args.min_sqft

    request = SearchRequest(location=args.location, criteria=criteria, label=args.label)

    db = db if db is not None else Database()
    DiscoveryAgent(db).sync_platforms(ALL_KNOWN_PLATFORMS)

    data_router = ProviderRouter(ProviderKind.DATA) if args.use_provider_router else None
    ai_router = ProviderRouter(ProviderKind.AI) if args.use_provider_router else None
    filter_engine = FilterEngine() if args.use_filter_engine else None
    geo_engine = GeographicEngine() if args.use_geo_engine else None
    ranking_engine_v2 = None
    if args.use_ranking_v2:
        profile = COMPREHENSIVE_PROFILE if args.ranking_profile == "comprehensive" else DEFAULT_PROFILE
        ranking_engine_v2 = RankingEngineV2(profile=profile)
    feedback_engine = FeedbackEngine() if args.feedback_profile_id else None

    agent = RentalResearchAgent(
        db,
        output_dir=output_dir,
        data_router=data_router,
        ai_router=ai_router,
        filter_engine=filter_engine,
        geo_engine=geo_engine,
        ranking_engine_v2=ranking_engine_v2,
        feedback_engine=feedback_engine,
        feedback_profile_id=args.feedback_profile_id,
        feedback_mode=FeedbackMode(args.feedback_mode),
    )
    result = agent.run(request)

    print(f"Search {result.search_id}: {len(result.apartments)} listing(s) processed.")
    print(f"Report: {result.report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
