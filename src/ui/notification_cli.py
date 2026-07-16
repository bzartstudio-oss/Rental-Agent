"""Notification Delivery CLI — a fifth, thin entry point (mirrors
`monitoring_cli.py`'s own "parses args, calls the real engine, prints the
result" role). Kept separate from `ui/cli.py`/`ui/feedback_cli.py`/
`ui/discovery_cli.py`/`ui/monitoring_cli.py` — none of the five command
surfaces grows to accommodate the others.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from src.core.config import DB_PATH
from src.feedback import FeedbackEngine
from src.notifications import NotificationEngine, feedback_integration, scheduling
from src.notifications import service as notification_service
from src.notifications import statistics as notification_statistics
from src.storage.database import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="notification-cli", description="Create notification preferences and deliver eligible monitoring events")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-preference", help="Create a new notification preference")
    create.add_argument("--profile-id", required=True)
    create.add_argument("--saved-search-id", default=None)
    create.add_argument("--channels", nargs="+", required=True, help="e.g. console file")
    create.add_argument("--immediate-event-types", nargs="*", default=[])
    create.add_argument("--digest-event-types", nargs="*", default=[])
    create.add_argument("--digest-frequency", default=None, choices=["hourly", "daily", "weekly", "manual", None])
    create.add_argument("--minimum-significance", type=float, default=0.0)
    create.add_argument("--minimum-severity", default=None, choices=["info", "warning", "critical", None])
    create.add_argument("--quiet-hours-start", default=None)
    create.add_argument("--quiet-hours-end", default=None)
    create.add_argument("--timezone", dest="timezone_name", default="UTC")
    create.add_argument("--max-per-hour", type=int, default=None)
    create.add_argument("--max-per-day", type=int, default=None)

    subparsers.add_parser("list-preferences", help="List every notification preference")

    view = subparsers.add_parser("view-preference", help="Show one preference's current version")
    view.add_argument("--preference-id", required=True)

    update = subparsers.add_parser("update-preference", help="Create a new immutable version of a preference")
    update.add_argument("--preference-id", required=True)
    update.add_argument("--channels", nargs="+", dest="enabled_channels", default=None)
    update.add_argument("--digest-frequency", default=None)
    update.add_argument("--quiet-hours-start", default=None)
    update.add_argument("--quiet-hours-end", default=None)

    enable = subparsers.add_parser("enable-notifications", help="Enable a preference")
    enable.add_argument("--preference-id", required=True)

    disable = subparsers.add_parser("disable-notifications", help="Disable a preference")
    disable.add_argument("--preference-id", required=True)

    preview = subparsers.add_parser("preview-notification", help="Render a notification without sending it")
    preview.add_argument("--preference-id", required=True)
    preview.add_argument("--event-ids", nargs="+", required=True)
    preview.add_argument("--channel", required=True)

    test = subparsers.add_parser("send-test-notification", help="Send a test notification through one channel")
    test.add_argument("--preference-id", required=True)
    test.add_argument("--channel", required=True)

    subparsers.add_parser("deliver-pending", help="Process every pending eligible immediate notification")

    digest = subparsers.add_parser("generate-digest", help="Generate one digest now for a preference (or every due preference)")
    digest.add_argument("--preference-id", default=None, help="Omit to run process_due_digests() for every preference")

    subparsers.add_parser("retry-due", help="Retry every delivery whose retry is due")

    list_deliveries = subparsers.add_parser("list-deliveries", help="List deliveries for a profile")
    list_deliveries.add_argument("--profile-id", required=True)

    list_failed = subparsers.add_parser("list-failed-deliveries", help="List failed deliveries")

    retry_one = subparsers.add_parser("retry-delivery", help="Retry one specific delivery now")
    retry_one.add_argument("--delivery-id", required=True)

    cancel = subparsers.add_parser("cancel-delivery", help="Cancel one pending/scheduled delivery")
    cancel.add_argument("--delivery-id", required=True)

    acknowledge = subparsers.add_parser("acknowledge-notification", help="Acknowledge one delivery, optionally recording a feedback reaction")
    acknowledge.add_argument("--delivery-id", required=True)
    acknowledge.add_argument("--acknowledged-by", default=None)
    acknowledge.add_argument("--note", default=None)
    acknowledge.add_argument("--reaction", default=None, choices=["notification_opened", "original_listing_opened", "dismissed", "saved", "rejected"])
    acknowledge.add_argument("--profile-id", default=None, help="Required together with --reaction")

    health = subparsers.add_parser("channel-health", help="Show one channel's recent delivery health")
    health.add_argument("--channel", required=True)

    stats = subparsers.add_parser("statistics", help="Show statistics for one delivery batch")
    stats.add_argument("--batch-id", required=True)

    export = subparsers.add_parser("export-history", help="Export delivery history for a profile as JSON")
    export.add_argument("--profile-id", required=True)

    subparsers.add_parser("task-scheduler-examples", help="Print cron/Task Scheduler command examples")

    return parser


def main(argv: list[str] | None = None, db: Database | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = db if db is not None else Database(db_path=DB_PATH)
    engine = NotificationEngine()
    now = datetime.now(timezone.utc)

    if args.command == "create-preference":
        preference = engine.create_preference(
            db, args.profile_id, saved_search_id=args.saved_search_id, enabled_channels=args.channels,
            immediate_event_types=args.immediate_event_types, digest_event_types=args.digest_event_types,
            digest_frequency=args.digest_frequency, minimum_significance=args.minimum_significance,
            minimum_severity=args.minimum_severity, quiet_hours_start=args.quiet_hours_start,
            quiet_hours_end=args.quiet_hours_end, timezone_name=args.timezone_name, max_per_hour=args.max_per_hour,
            max_per_day=args.max_per_day,
        )
        print(f"Created notification preference {preference.preference_id!r} for profile {args.profile_id!r}.")

    elif args.command == "list-preferences":
        with db.transaction() as conn:
            preferences = notification_service.get_all_preferences(conn)
        for p in preferences:
            print(f"  {p.preference_id} | profile={p.profile_id} | saved_search={p.saved_search_id} | version={p.current_version} enabled={p.enabled}")

    elif args.command == "view-preference":
        with db.transaction() as conn:
            preference = notification_service.get_preference(conn, args.preference_id)
            version = notification_service.get_latest_preference_version(conn, args.preference_id) if preference else None
        if preference is None:
            print(f"No such preference {args.preference_id!r}")
            return 1
        print(f"profile={preference.profile_id} version={preference.current_version} enabled={preference.enabled}")
        print(f"  channels={version.enabled_channels} immediate={version.immediate_event_types} digest={version.digest_event_types} digest_frequency={version.digest_frequency}")
        print(f"  quiet_hours={version.quiet_hours_start}-{version.quiet_hours_end} ({version.timezone}) max_per_hour={version.max_per_hour} max_per_day={version.max_per_day}")

    elif args.command == "update-preference":
        overrides = {}
        if args.enabled_channels is not None:
            overrides["enabled_channels"] = args.enabled_channels
        if args.digest_frequency is not None:
            overrides["digest_frequency"] = args.digest_frequency
        if args.quiet_hours_start is not None:
            overrides["quiet_hours_start"] = args.quiet_hours_start
        if args.quiet_hours_end is not None:
            overrides["quiet_hours_end"] = args.quiet_hours_end
        new_version = engine.update_preference(db, args.preference_id, **overrides)
        print(f"Created version {new_version.version} for preference {args.preference_id!r}.")

    elif args.command == "enable-notifications":
        engine.set_enabled(db, args.preference_id, True)
        print(f"Enabled preference {args.preference_id!r}.")

    elif args.command == "disable-notifications":
        engine.set_enabled(db, args.preference_id, False)
        print(f"Disabled preference {args.preference_id!r}.")

    elif args.command == "preview-notification":
        rendered = engine.preview(db, args.preference_id, args.event_ids, args.channel)
        print(rendered)

    elif args.command == "send-test-notification":
        result = engine.send_test_notification(db, args.preference_id, args.channel)
        print(f"success={result.success} error={result.error} duration_ms={result.duration_ms}")

    elif args.command == "deliver-pending":
        batch = engine.process_pending_deliveries(db)
        print(f"Batch {batch.batch_id}: attempted={batch.deliveries_attempted} succeeded={batch.deliveries_succeeded} failed={batch.deliveries_failed}")

    elif args.command == "generate-digest":
        if args.preference_id:
            delivery = engine.generate_digest(db, args.preference_id)
            print(f"Digest delivery: {delivery.delivery_id if delivery else '(no eligible events — nothing generated)'}")
        else:
            batch = engine.process_due_digests(db)
            print(f"Batch {batch.batch_id}: attempted={batch.deliveries_attempted} succeeded={batch.deliveries_succeeded} failed={batch.deliveries_failed}")

    elif args.command == "retry-due":
        batch = engine.retry_due_failures(db)
        print(f"Batch {batch.batch_id}: attempted={batch.deliveries_attempted} succeeded={batch.deliveries_succeeded} failed={batch.deliveries_failed}")

    elif args.command == "list-deliveries":
        with db.transaction() as conn:
            deliveries = notification_service.get_deliveries_for_profile(conn, args.profile_id)
        for d in deliveries:
            print(f"  {d.delivery_id} | status={d.status.value} channels={d.channels} events={d.event_ids} attempts={d.attempt_count}")

    elif args.command == "list-failed-deliveries":
        with db.transaction() as conn:
            deliveries = notification_service.get_deliveries_by_status(conn, "failed")
        for d in deliveries:
            print(f"  {d.delivery_id} | profile={d.profile_id} channels={d.channels} notes={d.notes}")

    elif args.command == "retry-delivery":
        delivery = engine.retry_delivery_now(db, args.delivery_id)
        print(f"Delivery {delivery.delivery_id}: status={delivery.status.value} attempts={delivery.attempt_count}")

    elif args.command == "cancel-delivery":
        delivery = engine.cancel_delivery(db, args.delivery_id)
        print(f"Delivery {delivery.delivery_id}: status={delivery.status.value}")

    elif args.command == "acknowledge-notification":
        engine.acknowledge(db, args.delivery_id, acknowledged_by=args.acknowledged_by, note=args.note)
        if args.reaction is not None:
            if not args.profile_id:
                print("--profile-id is required together with --reaction")
                return 1
            with db.transaction() as conn:
                feedback_integration.record_user_reaction(conn, FeedbackEngine(), args.profile_id, args.delivery_id, args.reaction, now)
        print(f"Acknowledged delivery {args.delivery_id!r}.")

    elif args.command == "channel-health":
        with db.transaction() as conn:
            health = notification_service.compute_channel_health(conn, args.channel)
        print(f"channel={health.channel} recent_success={health.recent_success_count} recent_failure={health.recent_failure_count} is_healthy={health.is_healthy}")
        print(f"last_success_at={health.last_success_at} last_failure_at={health.last_failure_at}")

    elif args.command == "statistics":
        with db.transaction() as conn:
            stats = notification_statistics.compute_statistics(conn, args.batch_id, now=now)
        for key, value in stats.as_dict().items():
            print(f"  {key}: {value}")

    elif args.command == "export-history":
        with db.transaction() as conn:
            deliveries = notification_service.get_deliveries_for_profile(conn, args.profile_id)
            export = []
            for d in deliveries:
                export.append({
                    "delivery_id": d.delivery_id, "status": d.status.value, "channels": d.channels,
                    "event_ids": d.event_ids, "is_digest": d.is_digest, "created_at": d.created_at.isoformat(),
                    "attempt_count": d.attempt_count, "acknowledged": d.acknowledged,
                })
        print(json.dumps(export, indent=2))

    elif args.command == "task-scheduler-examples":
        for name, command in scheduling.task_scheduler_command_examples().items():
            print(f"  {name}: {command}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
