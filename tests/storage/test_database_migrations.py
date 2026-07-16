"""Sprint V2.0.1 exit-criteria tests (docs/10_Roadmap.md "Migration Plan"): the migration
framework must migrate an existing (pre-migration) database in place, be safe to run on
every startup, roll back a failed migration completely, and apply migrations in numeric
version order regardless of filesystem/alphabetical ordering.

Every test uses a temporary `migrations_dir` (never the real `storage/migrations/`) so
these tests can inject deliberately broken or order-sensitive migration files without
touching real project migrations.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.storage.database import Database, _MIGRATIONS_DIR


class MigrationFromV1DatabaseTests(unittest.TestCase):
    """Simulates a database that predates migration 0001 — created with the base
    schema.sql only (schema_migrations table exists, but nothing has been recorded in
    it) — then opens it with the real migration in place and confirms it migrates
    successfully without losing existing data.
    """

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / "pre_migration.db"

        # An empty migrations_dir means only schema.sql applies — this is "a v1.1
        # database that has never seen migration 0001," created honestly (through the
        # same code path, not a hand-copied old schema file).
        empty_migrations_dir = Path(self._tmp_dir.name) / "no_migrations_yet"
        empty_migrations_dir.mkdir()
        Database(db_path=self.db_path, migrations_dir=empty_migrations_dir)

        # Insert a real v1.1-shaped row before any v2.0 columns exist, to prove it
        # survives the migration.
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO platforms (id, name, country, supported_cities, rental_types, "
            "homepage, requires_login, connector_available, discovery_method, created_at) "
            "VALUES ('pre_v2', 'Pre-V2 Platform', 'Testland', '[]', '[]', "
            "'https://example.com', 0, 1, 'manual', '2026-01-01T00:00:00+00:00')"
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_migrating_an_existing_database_preserves_old_data_and_adds_new_schema(self) -> None:
        # Real migrations directory this time — this is the actual upgrade happening.
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM platforms WHERE id = 'pre_v2'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["name"], "Pre-V2 Platform")  # old data intact
            self.assertIsNone(row["reliability_score"])  # new column, backfilled NULL

            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            self.assertIn("apartment_change_log", tables)
            self.assertIn("platform_performance_observations", tables)

            applied = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            self.assertEqual([r[0] for r in applied], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])  # every real migration applied, in order
        finally:
            conn.close()


class RepeatedStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / "test.db"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_starting_up_twice_does_not_reapply_or_error(self) -> None:
        Database(db_path=self.db_path)
        Database(db_path=self.db_path)  # must not raise

        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            self.assertEqual([r[0] for r in rows], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])  # each recorded exactly once, not twice
        finally:
            conn.close()


class FailedMigrationRollbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / "test.db"
        self.migrations_dir = Path(self._tmp_dir.name) / "migrations"
        self.migrations_dir.mkdir()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_a_failed_migration_is_fully_rolled_back_and_not_recorded(self) -> None:
        (self.migrations_dir / "0001_broken.sql").write_text(
            "CREATE TABLE IF NOT EXISTS rollback_test_table (id INTEGER);\n"
            "THIS IS NOT VALID SQL AND MUST FAIL;\n",
            encoding="utf-8",
        )

        with self.assertRaises(sqlite3.OperationalError):
            Database(db_path=self.db_path, migrations_dir=self.migrations_dir)

        conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            # The valid CREATE TABLE that ran before the bad statement must NOT have
            # survived — the whole migration is one transaction, not one-statement-at-a-time.
            self.assertNotIn("rollback_test_table", tables)

            applied = conn.execute("SELECT version FROM schema_migrations").fetchall()
            self.assertEqual(applied, [])  # not recorded as applied
        finally:
            conn.close()

    def test_after_a_failed_migration_is_fixed_it_can_be_retried_successfully(self) -> None:
        broken_path = self.migrations_dir / "0001_broken.sql"
        broken_path.write_text("THIS IS NOT VALID SQL;", encoding="utf-8")

        with self.assertRaises(sqlite3.OperationalError):
            Database(db_path=self.db_path, migrations_dir=self.migrations_dir)

        # Fix it in place (simulating a developer correcting the migration file) and retry.
        broken_path.write_text(
            "CREATE TABLE IF NOT EXISTS rollback_test_table (id INTEGER);", encoding="utf-8"
        )
        Database(db_path=self.db_path, migrations_dir=self.migrations_dir)  # must not raise this time

        conn = sqlite3.connect(self.db_path)
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            self.assertIn("rollback_test_table", tables)
            applied = conn.execute("SELECT version FROM schema_migrations").fetchall()
            self.assertEqual([r[0] for r in applied], [1])
        finally:
            conn.close()


class MigrationOrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / "test.db"
        self.migrations_dir = Path(self._tmp_dir.name) / "migrations"
        self.migrations_dir.mkdir()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_migrations_apply_in_numeric_not_alphabetical_order(self) -> None:
        # Deliberately unpadded version numbers: "10" sorts BEFORE "2" alphabetically,
        # but must run AFTER it numerically. If _discover_migrations() ever regressed to
        # naive string/filesystem sorting, this test would catch it.
        (self.migrations_dir / "1_create_marker.sql").write_text(
            "CREATE TABLE IF NOT EXISTS test_order_marker (value TEXT);", encoding="utf-8"
        )
        (self.migrations_dir / "2_insert_a.sql").write_text(
            "INSERT INTO test_order_marker (value) VALUES ('a');", encoding="utf-8"
        )
        (self.migrations_dir / "10_insert_b.sql").write_text(
            "INSERT INTO test_order_marker (value) VALUES ('b');", encoding="utf-8"
        )

        Database(db_path=self.db_path, migrations_dir=self.migrations_dir)

        conn = sqlite3.connect(self.db_path)
        try:
            applied = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            self.assertEqual([r[0] for r in applied], [1, 2, 10])

            values = conn.execute("SELECT value FROM test_order_marker ORDER BY rowid").fetchall()
            self.assertEqual([r[0] for r in values], ["a", "b"])  # 2 really ran before 10
        finally:
            conn.close()

    def test_migration_filename_without_a_numeric_prefix_raises_clearly(self) -> None:
        (self.migrations_dir / "not_numbered.sql").write_text(
            "CREATE TABLE IF NOT EXISTS whatever (id INTEGER);", encoding="utf-8"
        )

        with self.assertRaises(ValueError):
            Database(db_path=self.db_path, migrations_dir=self.migrations_dir)


class Migration0002IndexTests(unittest.TestCase):
    """v2.0 Step 4.5 architecture cleanup: 0002_search_requests_created_at_index.sql —
    added after the review found search_requests had no index beyond its primary key,
    despite being scanned and sorted by created_at on every completed search
    (search_memory_repository.find_previous_search/get_search_history).
    """

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / "test.db"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_the_index_exists_after_migration(self) -> None:
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)

        conn = sqlite3.connect(self.db_path)
        try:
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'search_requests'"
                ).fetchall()
            }
            self.assertIn("idx_search_requests_created_at", indexes)
        finally:
            conn.close()

    def test_applying_it_twice_does_not_error(self) -> None:
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)  # must not raise

        conn = sqlite3.connect(self.db_path)
        try:
            applied = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            self.assertEqual([row[0] for row in applied], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        finally:
            conn.close()


class Migration0003AnalysisMetricsColumnsTests(unittest.TestCase):
    """v2.0 Step 6: 0003_analysis_engine_metrics.sql — adds confidence/evidence_json/
    analyzer_version to apartment_analysis_metrics (schema-only since migration 0001).
    """

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / "test.db"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_the_new_columns_exist_after_migration(self) -> None:
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)

        conn = sqlite3.connect(self.db_path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(apartment_analysis_metrics)").fetchall()}
            self.assertIn("confidence", columns)
            self.assertIn("evidence_json", columns)
            self.assertIn("analyzer_version", columns)
        finally:
            conn.close()


class Migration0010NotificationTablesTests(unittest.TestCase):
    """Step 15: 0010_notification_delivery.sql — 12 tables for the Notification
    Delivery Engine (preferences/versions/templates/batches/deliveries/
    delivery-events/digests/attempts/messages/rate-limit and channel-health
    observations/acknowledgements) plus their indexes.
    """

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / "test.db"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_all_twelve_notification_tables_exist(self) -> None:
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)

        conn = sqlite3.connect(self.db_path)
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for expected in [
                "notification_preferences", "notification_preference_versions", "notification_templates",
                "notification_batches", "notification_deliveries", "notification_delivery_events",
                "notification_digests", "notification_attempts", "notification_messages",
                "rate_limit_observations", "channel_health_observations", "notification_acknowledgements",
            ]:
                self.assertIn(expected, tables)
        finally:
            conn.close()

    def test_key_indexes_exist(self) -> None:
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)

        conn = sqlite3.connect(self.db_path)
        try:
            indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
            for expected in [
                "idx_notif_deliveries_profile_created", "idx_notif_deliveries_status_next",
                "idx_notif_attempts_channel_status", "idx_notif_delivery_events_event",
                "idx_notif_deliveries_unacknowledged",
            ]:
                self.assertIn(expected, indexes)
        finally:
            conn.close()

    def test_applying_it_twice_does_not_error(self) -> None:
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)
        Database(db_path=self.db_path, migrations_dir=_MIGRATIONS_DIR)  # must not raise

        conn = sqlite3.connect(self.db_path)
        try:
            applied = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            self.assertEqual([row[0] for row in applied], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
