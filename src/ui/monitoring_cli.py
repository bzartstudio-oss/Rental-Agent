"""Continuous Monitoring & Saved Search CLI — a fourth, thin entry point
(mirrors `discovery_cli.py`'s own "parses args, calls the real engine, prints
the result" role). Kept separate from `ui/cli.py`/`ui/feedback_cli.py`/
`ui/discovery_cli.py` — none of the four command surfaces grows to
accommodate the others.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from src.core.config import DB_PATH
from src.feedback import FeedbackEngine
from src.monitoring import MonitoringEngine, MonitoringPolicy, feedback_integration, scheduling
from src.monitoring import service as monitoring_service
from src.monitoring import statistics as monitoring_statistics
from src.storage.database import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="monitoring-cli", description="Create and run saved searches, inspect monitoring events")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-saved-search", help="Create a new saved search")
    create.add_argument("--name", required=True)
    create.add_argument("--location", required=True)
    create.add_argument("--criteria-json", default="{}")
    create.add_argument("--profile-id", default=None)
    create.add_argument("--description", default=None)
    create.add_argument("--policy-json", default="{}", help="JSON overrides for MonitoringPolicy fields")
    create.add_argument("--selected-platforms", nargs="*", default=[])
    create.add_argument("--geographic-destinations-json", default="[]")

    subparsers.add_parser("list-saved-searches", help="List every saved search")

    view = subparsers.add_parser("view-saved-search", help="Show one saved search's current version")
    view.add_argument("--saved-search-id", required=True)

    update = subparsers.add_parser("update-saved-search", help="Create a new immutable version of a saved search")
    update.add_argument("--saved-search-id", required=True)
    update.add_argument("--location", default=None)
    update.add_argument("--criteria-json", default=None)
    update.add_argument("--policy-json", default=None)

    enable = subparsers.add_parser("enable-saved-search", help="Enable a saved search")
    enable.add_argument("--saved-search-id", required=True)

    disable = subparsers.add_parser("disable-saved-search", help="Disable a saved search")
    disable.add_argument("--saved-search-id", required=True)

    run_now = subparsers.add_parser("run-now", help="Run one saved search immediately")
    run_now.add_argument("--saved-search-id", required=True)

    subparsers.add_parser("run-due", help="Run every saved search whose schedule is due")

    list_runs = subparsers.add_parser("list-runs", help="List monitoring runs for a saved search")
    list_runs.add_argument("--saved-search-id", required=True)

    compare = subparsers.add_parser("compare-runs", help="Compare two monitoring runs")
    compare.add_argument("--previous-run-id", required=True)
    compare.add_argument("--current-run-id", required=True)

    list_events = subparsers.add_parser("list-events", help="List monitoring events for a saved search")
    list_events.add_argument("--saved-search-id", required=True)
    list_events.add_argument("--event-type", default=None)
    list_events.add_argument("--severity", default=None)

    acknowledge = subparsers.add_parser("acknowledge-event", help="Acknowledge one event, optionally recording a feedback reaction")
    acknowledge.add_argument("--event-id", required=True)
    acknowledge.add_argument("--acknowledged-by", default=None)
    acknowledge.add_argument("--note", default=None)
    acknowledge.add_argument("--reaction", default=None, choices=["saved", "ignored", "opened_original", "rejected"])
    acknowledge.add_argument("--profile-id", default=None, help="Required together with --reaction")

    export = subparsers.add_parser("export-events", help="Export every event for a saved search as JSON")
    export.add_argument("--saved-search-id", required=True)

    next_run = subparsers.add_parser("next-run", help="Show a saved search's next scheduled run time")
    next_run.add_argument("--saved-search-id", required=True)

    health = subparsers.add_parser("health", help="Show a saved search's operational health")
    health.add_argument("--saved-search-id", required=True)

    scheduler_examples = subparsers.add_parser("task-scheduler-examples", help="Print cron/Task Scheduler command examples")
    scheduler_examples.add_argument("--saved-search-id", required=True)

    return parser


def main(argv: list[str] | None = None, db: Database | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = db if db is not None else Database(db_path=DB_PATH)
    engine = MonitoringEngine()
    now = datetime.now(timezone.utc)

    if args.command == "create-saved-search":
        policy = MonitoringPolicy.from_dict({**MonitoringPolicy().as_dict(), **json.loads(args.policy_json)})
        saved_search = engine.create_saved_search(
            db, args.name, {"location": args.location, "criteria": json.loads(args.criteria_json)},
            profile_id=args.profile_id, description=args.description, monitoring_policy=policy,
            selected_platforms=args.selected_platforms, geographic_destinations=json.loads(args.geographic_destinations_json),
        )
        print(f"Created saved search {saved_search.saved_search_id!r} ({saved_search.name!r}), version 1.")

    elif args.command == "list-saved-searches":
        with db.transaction() as conn:
            saved_searches = monitoring_service.get_all_saved_searches(conn)
        for s in saved_searches:
            print(f"  {s.saved_search_id} | {s.name!r} | version={s.current_version} enabled={s.enabled}")

    elif args.command == "view-saved-search":
        with db.transaction() as conn:
            saved_search = monitoring_service.get_saved_search(conn, args.saved_search_id)
            version = monitoring_service.get_latest_saved_search_version(conn, args.saved_search_id) if saved_search else None
        if saved_search is None:
            print(f"No such saved search {args.saved_search_id!r}")
            return 1
        print(f"{saved_search.name!r} (version {saved_search.current_version}, enabled={saved_search.enabled})")
        print(f"  request: {version.request}")
        print(f"  monitoring_policy: {version.monitoring_policy.as_dict()}")

    elif args.command == "update-saved-search":
        overrides = {}
        if args.location is not None or args.criteria_json is not None:
            with db.transaction() as conn:
                current = monitoring_service.get_latest_saved_search_version(conn, args.saved_search_id)
            request = dict(current.request)
            if args.location is not None:
                request["location"] = args.location
            if args.criteria_json is not None:
                request["criteria"] = json.loads(args.criteria_json)
            overrides["request"] = request
        if args.policy_json is not None:
            with db.transaction() as conn:
                current = monitoring_service.get_latest_saved_search_version(conn, args.saved_search_id)
            overrides["monitoring_policy"] = MonitoringPolicy.from_dict({**current.monitoring_policy.as_dict(), **json.loads(args.policy_json)})
        new_version = engine.update_saved_search(db, args.saved_search_id, **overrides)
        print(f"Created version {new_version.version} for saved search {args.saved_search_id!r}.")

    elif args.command == "enable-saved-search":
        engine.set_enabled(db, args.saved_search_id, True)
        print(f"Enabled saved search {args.saved_search_id!r}.")

    elif args.command == "disable-saved-search":
        engine.set_enabled(db, args.saved_search_id, False)
        print(f"Disabled saved search {args.saved_search_id!r}.")

    elif args.command == "run-now":
        run = engine.run_now(db, args.saved_search_id)
        print(f"Monitoring run {run.monitoring_run_id} — status={run.status.value} events={run.event_count}")
        print(f"  platforms_succeeded={run.platforms_succeeded} platforms_failed={run.platforms_failed}")

    elif args.command == "run-due":
        runs = engine.run_due(db)
        print(f"Executed {len(runs)} due run(s).")
        for run in runs:
            print(f"  {run.saved_search_id} -> {run.monitoring_run_id} status={run.status.value} events={run.event_count}")

    elif args.command == "list-runs":
        with db.transaction() as conn:
            runs = monitoring_service.get_runs_for_saved_search(conn, args.saved_search_id)
        for run in runs:
            print(f"  {run.monitoring_run_id} | {run.started_at.isoformat()} | status={run.status.value} events={run.event_count}")

    elif args.command == "compare-runs":
        with db.transaction() as conn:
            comparison = monitoring_statistics.compare_monitoring_runs(conn, args.previous_run_id, args.current_run_id)
        print(f"Comparing {args.previous_run_id} -> {args.current_run_id}:")
        if comparison.search_comparison is not None:
            sc = comparison.search_comparison
            print(f"  new apartments: {sc.new_apartment_ids}")
            print(f"  removed apartments: {sc.removed_apartment_ids}")
            print(f"  price changes: {[(c.apartment_id, c.old_price, c.new_price) for c in sc.price_changes]}")
        print(f"  rank changes: {[(c.apartment_id, c.previous_rank, c.current_rank) for c in comparison.rank_changes if c.rank_delta]}")
        print(f"  better match: {comparison.better_match_apartment_id}")

    elif args.command == "list-events":
        with db.transaction() as conn:
            events = monitoring_service.get_events_for_saved_search(conn, args.saved_search_id, event_type=args.event_type, severity=args.severity)
        for event in events:
            print(f"  {event.event_id} | {event.event_type} | {event.severity} | sig={event.significance:.2f} | {event.explanation}")

    elif args.command == "acknowledge-event":
        with db.transaction() as conn:
            monitoring_service.acknowledge_event(conn, args.event_id, acknowledged_by=args.acknowledged_by, note=args.note, now=now)
            if args.reaction is not None:
                if not args.profile_id:
                    print("--profile-id is required together with --reaction")
                    return 1
                feedback_integration.record_user_reaction(conn, FeedbackEngine(), args.profile_id, args.event_id, args.reaction, now)
        print(f"Acknowledged event {args.event_id!r}.")

    elif args.command == "export-events":
        with db.transaction() as conn:
            events = monitoring_service.get_events_for_saved_search(conn, args.saved_search_id)
        print(json.dumps([
            {
                "event_id": e.event_id, "event_type": e.event_type, "severity": e.severity, "significance": e.significance,
                "explanation": e.explanation, "old_value": e.old_value, "new_value": e.new_value,
                "detected_at": e.detected_at.isoformat(), "acknowledged": e.acknowledged,
            }
            for e in events
        ], indent=2))

    elif args.command == "next-run":
        with db.transaction() as conn:
            next_run_at = scheduling.next_run_time(conn, args.saved_search_id)
        print(f"Next run: {next_run_at.isoformat() if next_run_at else 'manual only (no schedule configured)'}")

    elif args.command == "health":
        with db.transaction() as conn:
            health = scheduling.compute_health(conn, args.saved_search_id)
        print(f"enabled={health.enabled} last_run_status={health.last_run_status} last_run_at={health.last_run_at}")
        print(f"next_run_at={health.next_run_at} is_claimed={health.is_claimed} consecutive_failures={health.consecutive_failure_count}")
        print(f"is_healthy={health.is_healthy}")

    elif args.command == "task-scheduler-examples":
        examples = scheduling.task_scheduler_command_examples(args.saved_search_id, str(DB_PATH))
        for name, command in examples.items():
            print(f"  {name}: {command}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
