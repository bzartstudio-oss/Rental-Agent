"""Production-quality local backup — see docs/35_Installation_and_Operations.md
"Backup and Restore". Never includes secrets: `.env`, `data/.web_secret_key`,
and any notification channel credentials are always excluded — only the
SQLite database, raw pages, cached media, generated reports/notification
files, non-secret configuration, migration state, and release metadata are
backed up.

Usage:
    python scripts/backup.py [--destination DIR] [--compress] [--label NAME]

Manifest (`manifest.json`, written inside the backup folder): every included
file's relative path, size, and SHA-256 checksum, plus `migration_versions`
(from `schema_migrations`) and `release` metadata (git commit hash if
available, `VERSION` file contents).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import DATA_DIR, DB_PATH, OUTPUT_DIR  # noqa: E402

DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "backups"

# Never included in a backup, under any circumstances.
_EXCLUDED_NAMES = {".env", ".web_secret_key"}


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _migration_versions_at(db_path: Path) -> list[int]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        return [row[0] for row in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _git_commit_hash() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _version_file_contents() -> str | None:
    version_path = PROJECT_ROOT / "VERSION"
    return version_path.read_text(encoding="utf-8").strip() if version_path.exists() else None


def _backup_database(db_path: Path, dest_dir: Path) -> Path | None:
    """Uses SQLite's own online backup API — safe even if another process
    has the database open, unlike a plain file copy which could capture a
    half-written page.
    """
    if not db_path.exists():
        return None
    dest_path = dest_dir / "rental_intelligence.db"
    source_conn = sqlite3.connect(db_path)
    dest_conn = sqlite3.connect(dest_path)
    try:
        source_conn.backup(dest_conn)
    finally:
        source_conn.close()
        dest_conn.close()
    return dest_path


def _copy_directory(source: Path, dest: Path) -> list[Path]:
    copied: list[Path] = []
    if not source.exists():
        return copied
    for item in source.rglob("*"):
        if item.is_dir():
            continue
        if item.name in _EXCLUDED_NAMES:
            continue
        relative = item.relative_to(source)
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(target)
    return copied


def create_backup(
    destination_root: Path = DEFAULT_BACKUP_ROOT, *, compress: bool = False, label: str | None = None,
    db_path: Path = DB_PATH, data_dir: Path = DATA_DIR, output_dir: Path = OUTPUT_DIR,
) -> Path:
    """Creates one timestamped backup under `destination_root`. Returns the
    path to the backup folder (or the `.zip` archive if `compress=True`).

    `db_path`/`data_dir`/`output_dir` default to the real project paths —
    the parameters exist so tests can point this at a temporary,
    fully-isolated source instead of ever touching real accumulated data,
    the same `db: Database | None = None`-style pattern every CLI in this
    codebase already uses.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder_name = f"backup_{timestamp}" + (f"_{label}" if label else "")
    backup_dir = destination_root / folder_name
    backup_dir.mkdir(parents=True, exist_ok=False)

    manifest_files: list[dict] = []

    db_backup_path = _backup_database(db_path, backup_dir)
    if db_backup_path is not None:
        manifest_files.append({"path": db_backup_path.name, "size": db_backup_path.stat().st_size, "sha256": _sha256_of(db_backup_path)})

    for subdir_name, source_dir in (
        ("raw_pages", data_dir / "raw_pages"),
        ("media", data_dir / "media"),
        ("output", output_dir),
    ):
        dest_subdir = backup_dir / subdir_name
        for copied_path in _copy_directory(source_dir, dest_subdir):
            manifest_files.append({
                "path": str(copied_path.relative_to(backup_dir)),
                "size": copied_path.stat().st_size,
                "sha256": _sha256_of(copied_path),
            })

    # Non-secret configuration: `.env.example` only, never `.env` itself.
    env_example = PROJECT_ROOT / ".env.example"
    if env_example.exists():
        target = backup_dir / "config" / ".env.example"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(env_example, target)
        manifest_files.append({"path": str(target.relative_to(backup_dir)), "size": target.stat().st_size, "sha256": _sha256_of(target)})

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "release": {"commit_hash": _git_commit_hash(), "version": _version_file_contents()},
        "migration_versions": _migration_versions_at(db_path),
        "files": manifest_files,
    }
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if compress:
        archive_path = backup_dir.with_suffix(".zip")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in backup_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(backup_dir))
        shutil.rmtree(backup_dir)
        return archive_path

    return backup_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backup", description="Back up the Rental Intelligence Platform's local data")
    parser.add_argument("--destination", type=Path, default=DEFAULT_BACKUP_ROOT, help="Directory to write the timestamped backup into")
    parser.add_argument("--compress", action="store_true", help="Write a single .zip archive instead of a folder")
    parser.add_argument("--label", default=None, help="Optional label appended to the backup's folder/archive name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = create_backup(args.destination, compress=args.compress, label=args.label)
    print(f"Backup written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
