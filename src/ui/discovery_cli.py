"""Automatic Platform Discovery CLI — a third, thin entry point (mirrors
`feedback_cli.py`'s own "parses args, calls the real engine, prints the result"
role) for the mission's own CLI section: discover, list-discovered,
list-verified, list-unsupported, list-missing-connectors, compare-runs,
approve-candidate/reject-candidate (the mission's "approve-or-reject-candidate"
as two explicit subcommands), view-evidence, view-coverage-summary. Kept
separate from `ui/cli.py`/`ui/feedback_cli.py` — platform discovery is a
distinct operation from running a search or recording feedback, so none of the
three command surfaces grows to accommodate the others.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from src.core.config import DB_PATH
from src.discovery.automatic import AutomaticDiscoveryAgent, DiscoveryPolicy, DiscoveryRequest, PlatformEvidence, PlatformStatus
from src.discovery.automatic import report as discovery_report
from src.discovery.automatic import service as discovery_service
from src.discovery.automatic.agent import UNSUPPORTED_STATUSES
from src.discovery.discovery_agent import DiscoveryAgent, PlatformCandidate as SyncPlatformCandidate
from src.storage.database import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discovery-cli", description="Discover and manage rental-platform candidates")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Run a discovery pass for a country/region/city")
    discover.add_argument("--country", default=None)
    discover.add_argument("--region", default=None)
    discover.add_argument("--city", default=None)
    discover.add_argument("--language", default=None)
    discover.add_argument("--rental-category", dest="rental_categories", action="append", default=[])
    discover.add_argument("--manual-url", dest="manual_urls", action="append", default=[])
    discover.add_argument("--provider", dest="discovery_providers", action="append", default=None)
    discover.add_argument("--minimum-confidence", type=float, default=0.0)
    discover.add_argument("--max-age-days", type=float, default=30.0)
    discover.add_argument("--force-refresh", action="store_true")
    discover.add_argument("--report", action="store_true", help="Also write an HTML+JSON discovery report")

    subparsers.add_parser("list-discovered", help="List every discovered candidate")
    subparsers.add_parser("list-verified", help="List candidates that passed domain verification")
    subparsers.add_parser("list-unsupported", help="List candidates with no active connector yet")
    subparsers.add_parser("list-missing-connectors", help="List verified candidates specifically missing a connector")

    compare = subparsers.add_parser("compare-runs", help="Compare two discovery runs")
    compare.add_argument("--previous-run-id", required=True)
    compare.add_argument("--current-run-id", required=True)

    approve = subparsers.add_parser("approve-candidate", help="Promote a candidate into the Platform Registry")
    approve.add_argument("--candidate-id", required=True)
    approve.add_argument("--connector-name", default=None)

    reject = subparsers.add_parser("reject-candidate", help="Mark a candidate as rejected/unsupported")
    reject.add_argument("--candidate-id", required=True)
    reject.add_argument("--reason", default=None)

    evidence = subparsers.add_parser("view-evidence", help="Show every evidence row collected for one candidate")
    evidence.add_argument("--candidate-id", required=True)

    subparsers.add_parser("view-coverage-summary", help="Show aggregate discovery statistics")

    return parser


def main(argv: list[str] | None = None, db: Database | None = None) -> int:
    """`db` defaults to the real project database — the parameter exists so tests
    can point the CLI at a temporary database instead.
    """
    args = build_parser().parse_args(argv)
    db = db if db is not None else Database(db_path=DB_PATH)
    agent = AutomaticDiscoveryAgent()

    if args.command == "discover":
        request = DiscoveryRequest(
            country=args.country, region=args.region, city=args.city, language=args.language,
            rental_categories=args.rental_categories, manual_urls=args.manual_urls,
            discovery_providers=args.discovery_providers, minimum_confidence=args.minimum_confidence,
            refresh_policy=DiscoveryPolicy(max_age_days=args.max_age_days, force_refresh=args.force_refresh),
        )
        with db.transaction() as conn:
            result = agent.run(conn, request)
            if args.report:
                json_path, html_path = discovery_report.generate_report(conn, result)
        print(f"Discovery run {result.run.run_id} — providers used: {result.run.providers_used}")
        print(f"  total={result.run.total_candidates} new={result.run.new_candidate_count} "
              f"duplicates={result.run.duplicate_count} supported={result.run.supported_count} "
              f"unsupported={result.run.unsupported_count}")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        if args.report:
            print(f"  report: {json_path}")
            print(f"  report: {html_path}")

    elif args.command == "list-discovered":
        with db.transaction() as conn:
            candidates = discovery_service.get_all_candidates(conn)
        _print_candidates(candidates)

    elif args.command == "list-verified":
        with db.transaction() as conn:
            candidates = [
                c for c in discovery_service.get_all_candidates(conn) if c.status is not PlatformStatus.DISCOVERED
                and c.status is not PlatformStatus.INACCESSIBLE
            ]
        _print_candidates(candidates)

    elif args.command == "list-unsupported":
        with db.transaction() as conn:
            candidates = [c for c in discovery_service.get_all_candidates(conn) if c.status in UNSUPPORTED_STATUSES]
        _print_candidates(candidates)

    elif args.command == "list-missing-connectors":
        with db.transaction() as conn:
            candidates = agent.platforms_missing_connectors(conn)
        _print_candidates(candidates)

    elif args.command == "compare-runs":
        with db.transaction() as conn:
            comparison = agent.compare_discovery_runs(conn, args.previous_run_id, args.current_run_id)
        print(f"Comparing {args.previous_run_id} -> {args.current_run_id}:")
        print(f"  new candidates: {comparison.new_candidate_ids}")
        print(f"  removed/unreachable: {comparison.removed_or_unreachable_candidate_ids}")
        print(f"  changed verification status: {comparison.changed_verification_status_candidate_ids}")
        print(f"  changed connector availability: {comparison.changed_connector_availability_candidate_ids}")
        print(f"  newly supported locations: {comparison.newly_supported_locations}")

    elif args.command == "approve-candidate":
        with db.transaction() as conn:
            candidate = discovery_service.get_candidate(conn, args.candidate_id)
        if candidate is None:
            print(f"No such candidate {args.candidate_id!r}")
            return 1
        sync_candidate = SyncPlatformCandidate(
            platform_id=candidate.matched_platform_id or candidate.normalized_domain.replace(".", "_"),
            name=candidate.name, country=candidate.country or "unknown", homepage=candidate.raw_url,
            connector_available=candidate.status is PlatformStatus.CONNECTOR_AVAILABLE,
            connector_name=args.connector_name, discovery_method="automatic_discovery_approved",
            notes=f"Approved from discovery candidate {candidate.candidate_id} (classification={candidate.classification.value})",
        )
        report = DiscoveryAgent(db).sync_platforms([sync_candidate])
        print(f"Approved candidate {args.candidate_id!r}: new={report.new_platforms} updated={report.updated_platforms}")

    elif args.command == "reject-candidate":
        with db.transaction() as conn:
            candidate = discovery_service.get_candidate(conn, args.candidate_id)
            if candidate is None:
                print(f"No such candidate {args.candidate_id!r}")
                return 1
            candidate.status = PlatformStatus.UNSUPPORTED
            discovery_service.update_candidate(conn, candidate)
            discovery_service.record_evidence(
                conn,
                PlatformEvidence(
                    candidate_id=candidate.candidate_id, run_id=candidate.last_run_id,
                    evidence_type="manual_review_decision", discovery_provider="cli",
                    value={"decision": "rejected", "reason": args.reason}, collected_at=datetime.now(timezone.utc),
                ),
            )
        print(f"Rejected candidate {args.candidate_id!r}.")

    elif args.command == "view-evidence":
        with db.transaction() as conn:
            evidence_rows = discovery_service.get_evidence_for_candidate(conn, args.candidate_id)
        for item in evidence_rows:
            print(f"  [{item.collected_at.isoformat()}] {item.evidence_type} (via {item.discovery_provider!r}): {item.value}")

    elif args.command == "view-coverage-summary":
        with db.transaction() as conn:
            stats = agent.coverage_summary(conn)
        for key, value in stats.as_dict().items():
            print(f"  {key}: {value}")

    return 0


def _print_candidates(candidates) -> None:
    for candidate in candidates:
        print(f"  {candidate.candidate_id} | {candidate.name} | {candidate.normalized_domain} | "
              f"status={candidate.status.value} classification={candidate.classification.value} "
              f"confidence={candidate.confidence}")


if __name__ == "__main__":
    sys.exit(main())
