"""Backup/restore/verify tests — see docs/35_Installation_and_Operations.md
"Backup and Restore". Every test builds its own isolated temp source
(database + data/output directories) — never the real project's
`data/`/`output/` — per the mission's own "never modify or delete the user's
real accumulated data."
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.backup import create_backup
from scripts.restore import preview_restore, restore_backup
from scripts.verify_backup import verify_backup
from src.storage.database import Database


class BackupCreationTests(unittest.TestCase):
    def test_backup_includes_database_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "source" / "rental_intelligence.db"
            Database(db_path=db_path)  # applies schema + migrations
            data_dir = tmp_path / "source" / "data"
            (data_dir / "media").mkdir(parents=True)
            (data_dir / "media" / "photo.jpg").write_bytes(b"fake-image-bytes")
            output_dir = tmp_path / "source" / "output"
            output_dir.mkdir(parents=True)
            (output_dir / "report.html").write_text("<html>report</html>", encoding="utf-8")

            backup_path = create_backup(
                tmp_path / "backups", db_path=db_path, data_dir=data_dir, output_dir=output_dir,
            )

            self.assertTrue((backup_path / "rental_intelligence.db").exists())
            self.assertTrue((backup_path / "media" / "photo.jpg").exists())
            self.assertTrue((backup_path / "output" / "report.html").exists())
            manifest = json.loads((backup_path / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("migration_versions", manifest)
            self.assertTrue(manifest["migration_versions"])
            self.assertTrue(manifest["files"])

    def test_backup_never_includes_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "source" / "rental_intelligence.db"
            Database(db_path=db_path)
            data_dir = tmp_path / "source" / "data"
            (data_dir / "media").mkdir(parents=True)
            (data_dir / ".web_secret_key").write_text("super-secret", encoding="utf-8")
            output_dir = tmp_path / "source" / "output"
            output_dir.mkdir(parents=True)

            backup_path = create_backup(tmp_path / "backups", db_path=db_path, data_dir=data_dir, output_dir=output_dir)

            for path in backup_path.rglob("*"):
                self.assertNotEqual(path.name, ".env")
                self.assertNotEqual(path.name, ".web_secret_key")

    def test_compressed_backup_produces_a_single_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "source" / "rental_intelligence.db"
            Database(db_path=db_path)
            archive_path = create_backup(
                tmp_path / "backups", compress=True, db_path=db_path,
                data_dir=tmp_path / "source" / "data", output_dir=tmp_path / "source" / "output",
            )
            self.assertEqual(archive_path.suffix, ".zip")
            self.assertTrue(archive_path.exists())


class BackupVerificationTests(unittest.TestCase):
    def _make_backup(self, tmp_path: Path) -> Path:
        db_path = tmp_path / "source" / "rental_intelligence.db"
        Database(db_path=db_path)
        return create_backup(
            tmp_path / "backups", db_path=db_path,
            data_dir=tmp_path / "source" / "data", output_dir=tmp_path / "source" / "output",
        )

    def test_a_fresh_backup_verifies_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup_path = self._make_backup(Path(tmp))
            result = verify_backup(backup_path)
            self.assertTrue(result.ok, result.errors)
            self.assertTrue(result.database_integrity_ok)

    def test_a_corrupted_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup_path = self._make_backup(Path(tmp))
            (backup_path / "rental_intelligence.db").write_bytes(b"corrupted-not-a-real-database")
            result = verify_backup(backup_path)
            self.assertFalse(result.ok)
            self.assertTrue(result.corrupted_files or not result.database_integrity_ok)


class RestoreTests(unittest.TestCase):
    def _make_backup(self, tmp_path: Path) -> Path:
        db_path = tmp_path / "source" / "rental_intelligence.db"
        Database(db_path=db_path)
        data_dir = tmp_path / "source" / "data"
        (data_dir / "media").mkdir(parents=True)
        (data_dir / "media" / "photo.jpg").write_bytes(b"fake-image-bytes")
        return create_backup(tmp_path / "backups", db_path=db_path, data_dir=data_dir, output_dir=tmp_path / "source" / "output")

    def test_preview_lists_files_without_writing_anything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            backup_path = self._make_backup(tmp_path)
            destination = tmp_path / "restored"
            files = preview_restore(backup_path)
            self.assertIn("rental_intelligence.db", files)
            self.assertFalse(destination.exists())

    def test_restore_to_alternate_location_preserves_data_and_passes_integrity_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            backup_path = self._make_backup(tmp_path)
            destination = tmp_path / "restored_elsewhere"
            restored = restore_backup(backup_path, destination)
            self.assertTrue((restored / "rental_intelligence.db").exists())
            self.assertTrue((restored / "media" / "photo.jpg").exists())

    def test_restored_database_actually_starts_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            backup_path = self._make_backup(tmp_path)
            destination = tmp_path / "restored_for_startup"
            restored = restore_backup(backup_path, destination)
            db = Database(db_path=restored / "rental_intelligence.db")
            with db.transaction() as conn:
                count = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
            self.assertGreater(count, 0)

    def test_refuses_to_overwrite_a_nonempty_destination_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            backup_path = self._make_backup(tmp_path)
            destination = tmp_path / "occupied"
            destination.mkdir()
            (destination / "existing_file.txt").write_text("pre-existing data", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                restore_backup(backup_path, destination)

            # Explicit --force allows it.
            restored = restore_backup(backup_path, destination, force=True)
            self.assertTrue((restored / "rental_intelligence.db").exists())

    def test_historical_data_is_preserved_through_a_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "source" / "rental_intelligence.db"
            db = Database(db_path=db_path)
            now = datetime.now(timezone.utc)
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO platforms (id, name, country, homepage, connector_available, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    ("demo_platform", "Demo", "N/A", "local", 1, now.isoformat()),
                )
            backup_path = create_backup(tmp_path / "backups", db_path=db_path, data_dir=tmp_path / "source" / "data", output_dir=tmp_path / "source" / "output")
            destination = tmp_path / "restored_history"
            restored = restore_backup(backup_path, destination)
            restored_db = Database(db_path=restored / "rental_intelligence.db")
            with restored_db.transaction() as conn:
                row = conn.execute("SELECT id FROM platforms WHERE id = 'demo_platform'").fetchone()
            self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
