"""Tests for the Feedback & Preference CLI — src/ui/feedback_cli.py."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.discovery import platform_registry
from src.storage import apartment_repository
from src.storage.database import Database
from src.storage.models import Apartment, Platform
from src.ui import feedback_cli


class FeedbackCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            platform_registry.register_platform(
                conn, Platform(id="p1", name="P1", country="N/A", homepage="n/a",
                                connector_available=False, connector_name=None, created_at=now),
            )
            apartment_repository.insert_apartment(
                conn, Apartment(id="apt-1", platform_id="p1", platform_listing_id="l1", title="T", url="u",
                                 current_price=1000, current_status="available", first_seen_at=now, last_seen_at=now,
                                 property_type="apartment"),
            )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_record_and_export_round_trip(self) -> None:
        exit_code = feedback_cli.main(
            ["record", "--profile-id", "u1", "--event-type", "saved", "--apartment-id", "apt-1"], db=self.db,
        )
        self.assertEqual(exit_code, 0)

    def test_profile_command_runs_without_crashing(self) -> None:
        feedback_cli.main(["record", "--profile-id", "u1", "--event-type", "saved", "--apartment-id", "apt-1"], db=self.db)
        exit_code = feedback_cli.main(["profile", "--profile-id", "u1"], db=self.db)
        self.assertEqual(exit_code, 0)

    def test_reset_command_runs_without_crashing(self) -> None:
        feedback_cli.main(["record", "--profile-id", "u1", "--event-type", "saved", "--apartment-id", "apt-1"], db=self.db)
        feedback_cli.main(["profile", "--profile-id", "u1"], db=self.db)
        exit_code = feedback_cli.main(["reset", "--profile-id", "u1"], db=self.db)
        self.assertEqual(exit_code, 0)

    def test_explain_and_history_commands_run_without_crashing(self) -> None:
        feedback_cli.main(["record", "--profile-id", "u1", "--event-type", "saved", "--apartment-id", "apt-1"], db=self.db)
        feedback_cli.main(["profile", "--profile-id", "u1"], db=self.db)
        self.assertEqual(feedback_cli.main(["explain", "--profile-id", "u1", "--preference-key", "property_type"], db=self.db), 0)
        self.assertEqual(feedback_cli.main(["history", "--profile-id", "u1", "--preference-key", "property_type"], db=self.db), 0)

    def test_unknown_event_type_is_rejected_by_argparse(self) -> None:
        with self.assertRaises(SystemExit):
            feedback_cli.main(["record", "--profile-id", "u1", "--event-type", "not_a_real_type"], db=self.db)


if __name__ == "__main__":
    unittest.main()
