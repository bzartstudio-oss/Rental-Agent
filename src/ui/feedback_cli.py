"""Feedback & Preference CLI — a second, thin entry point (mirrors `rental_agent.py`'s
own "parses args, calls the real engine, prints the result" role) for the commands
the mission's REPORT AND UI INTEGRATION section asks for: recording feedback,
viewing the current preference profile, viewing explanations, resetting inferred
preferences, and selecting preference mode. Kept separate from `ui/cli.py` (the
search command) rather than folded into it — recording feedback/inspecting
preferences is a genuinely different operation from running a search, and keeping
them apart means neither command's argument surface grows to accommodate the
other, preserving `ui/cli.py`'s "Maintain backward compatibility" guarantee.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from src.core.config import DB_PATH
from src.feedback import FeedbackEngine, FeedbackEvent, FeedbackMode
from src.feedback.event_types import KNOWN_EVENT_TYPES
from src.storage import apartment_repository
from src.storage.database import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="feedback-cli", description="Record and inspect user feedback/preferences")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="Record one feedback event")
    record.add_argument("--profile-id", required=True)
    record.add_argument("--event-type", required=True, choices=sorted(KNOWN_EVENT_TYPES))
    record.add_argument("--apartment-id", default=None)
    record.add_argument("--search-id", default=None)
    record.add_argument("--value", default=None, help="JSON-encoded event_value, e.g. '{\"rating\": 4}'")
    record.add_argument("--source", default="cli")

    profile = subparsers.add_parser("profile", help="Build and print the current preference profile")
    profile.add_argument("--profile-id", required=True)
    profile.add_argument("--mode", default="suggested", choices=[m.value for m in FeedbackMode])

    explain = subparsers.add_parser("explain", help="Explain one preference's evidence")
    explain.add_argument("--profile-id", required=True)
    explain.add_argument("--preference-key", required=True)

    history = subparsers.add_parser("history", help="Show one preference's adjustment history")
    history.add_argument("--profile-id", required=True)
    history.add_argument("--preference-key", required=True)

    undo = subparsers.add_parser("undo", help="Undo one specific preference adjustment")
    undo.add_argument("--profile-id", required=True)
    undo.add_argument("--preference-key", required=True)
    undo.add_argument("--adjustment-id", required=True, type=int)

    reset = subparsers.add_parser("reset", help="Reset every inferred preference to neutral (explicit ones untouched)")
    reset.add_argument("--profile-id", required=True)

    export = subparsers.add_parser("export", help="Export the full raw feedback event history")
    export.add_argument("--profile-id", required=True)

    return parser


def main(argv: list[str] | None = None, db: Database | None = None) -> int:
    """`db` defaults to the real project database — the parameter exists so tests
    can point the CLI at a temporary database instead.
    """
    args = build_parser().parse_args(argv)
    db = db if db is not None else Database(db_path=DB_PATH)
    engine = FeedbackEngine()
    now = datetime.now(timezone.utc)

    if args.command == "record":
        event = FeedbackEvent(
            profile_id=args.profile_id, event_type=args.event_type, occurred_at=now, source=args.source,
            apartment_id=args.apartment_id, search_id=args.search_id,
            event_value=json.loads(args.value) if args.value else {},
        )
        with db.transaction() as conn:
            apartment = apartment_repository.get_apartment(conn, args.apartment_id) if args.apartment_id else None
            engine.record_event(conn, event, apartment=apartment)
        print(f"Recorded event {event.event_id} ({event.event_type}) for profile {args.profile_id!r}.")

    elif args.command == "profile":
        with db.transaction() as conn:
            profile = engine.build_preference_profile(conn, args.profile_id, mode=FeedbackMode(args.mode))
        print(f"Preference profile for {args.profile_id!r} (mode: {profile.mode.value}):")
        for key, value in sorted(profile.preferences.items()):
            if value.current_value is None:
                continue
            kind = "explicit" if value.is_explicit else "inferred"
            print(f"  {key}: {value.current_value} (confidence {value.confidence.overall:.2f}, {kind})")

    elif args.command == "explain":
        with db.transaction() as conn:
            evidence = engine.explain_preference(conn, args.profile_id, args.preference_key)
        print(f"Evidence for {args.preference_key!r} (profile {args.profile_id!r}):")
        print(f"  supporting={evidence.supporting_count} opposing={evidence.opposing_count} "
              f"explicit={evidence.explicit_count} inferred={evidence.inferred_count}")
        for obs in evidence.observations:
            print(f"  - [{obs.direction}/{obs.source_type}] {obs.explanation}")

    elif args.command == "history":
        with db.transaction() as conn:
            adjustments = engine.get_preference_history(conn, args.profile_id, args.preference_key)
        for adjustment in adjustments:
            print(f"  #{adjustment.id} [{adjustment.adjustment_type}] {adjustment.previous_value} -> "
                  f"{adjustment.new_value} ({adjustment.reason})")

    elif args.command == "undo":
        with db.transaction() as conn:
            undo = engine.undo_preference_adjustment(conn, args.profile_id, args.preference_key, args.adjustment_id)
        print(f"Undo recorded as adjustment #{undo.id}: restored value {undo.new_value!r}.")

    elif args.command == "reset":
        with db.transaction() as conn:
            resets = engine.reset_inferred_preferences(conn, args.profile_id)
        print(f"Reset {len(resets)} inferred preference(s) for profile {args.profile_id!r}. Explicit preferences untouched.")

    elif args.command == "export":
        with db.transaction() as conn:
            events = engine.export_feedback_history(conn, args.profile_id)
        for event in events:
            print(f"  [{event.occurred_at.isoformat()}] {event.event_type} apartment={event.apartment_id} value={event.event_value}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
