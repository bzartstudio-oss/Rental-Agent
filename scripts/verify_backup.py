"""Verify a backup's integrity without restoring it — see
docs/35_Installation_and_Operations.md "Backup and Restore".

Usage:
    python scripts/verify_backup.py PATH_TO_BACKUP [--json]

Checks every file listed in the backup's `manifest.json` against its
recorded SHA-256 checksum and size, and runs `PRAGMA integrity_check` against
the backed-up database. Works against either a backup folder or a `.zip`
archive produced by `scripts/backup.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class BackupVerificationResult:
    ok: bool
    checked_files: int
    corrupted_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    database_integrity_ok: bool | None = None
    errors: list[str] = field(default_factory=list)


def _resolve_backup_dir(backup_path: Path, extract_dir: Path) -> Path:
    if backup_path.is_dir():
        return backup_path
    if backup_path.suffix == ".zip":
        with zipfile.ZipFile(backup_path) as archive:
            archive.extractall(extract_dir)
        return extract_dir
    raise ValueError(f"{backup_path} is neither a backup folder nor a .zip archive")


def verify_backup(backup_path: Path) -> BackupVerificationResult:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            backup_dir = _resolve_backup_dir(backup_path, Path(tmp))
        except ValueError as exc:
            return BackupVerificationResult(ok=False, checked_files=0, errors=[str(exc)])

        manifest_path = backup_dir / "manifest.json"
        if not manifest_path.exists():
            return BackupVerificationResult(ok=False, checked_files=0, errors=["manifest.json not found in backup"])

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = BackupVerificationResult(ok=True, checked_files=0)

        for entry in manifest.get("files", []):
            file_path = backup_dir / entry["path"]
            if not file_path.exists():
                result.missing_files.append(entry["path"])
                result.ok = False
                continue
            result.checked_files += 1
            if file_path.stat().st_size != entry["size"]:
                result.corrupted_files.append(entry["path"])
                result.ok = False
                continue
            if _sha256_of(file_path) != entry["sha256"]:
                result.corrupted_files.append(entry["path"])
                result.ok = False

        db_path = backup_dir / "rental_intelligence.db"
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                result.database_integrity_ok = row is not None and row[0] == "ok"
                if not result.database_integrity_ok:
                    result.ok = False
            except sqlite3.Error as exc:
                result.database_integrity_ok = False
                result.ok = False
                result.errors.append(f"database integrity check failed: {exc}")
            finally:
                conn.close()

        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify_backup", description="Verify a backup's checksums and database integrity")
    parser.add_argument("backup_path", type=Path)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of a summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify_backup(args.backup_path)

    if args.json:
        print(json.dumps({
            "ok": result.ok, "checked_files": result.checked_files, "corrupted_files": result.corrupted_files,
            "missing_files": result.missing_files, "database_integrity_ok": result.database_integrity_ok, "errors": result.errors,
        }, indent=2))
    else:
        print(f"Backup: {args.backup_path}")
        print(f"Files checked: {result.checked_files}")
        print(f"Corrupted files: {result.corrupted_files or 'none'}")
        print(f"Missing files: {result.missing_files or 'none'}")
        print(f"Database integrity: {result.database_integrity_ok}")
        if result.errors:
            print(f"Errors: {result.errors}")
        print("PASS" if result.ok else "FAIL")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
