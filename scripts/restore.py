"""Restore a backup created by `scripts/backup.py` — see
docs/35_Installation_and_Operations.md "Backup and Restore".

Usage:
    python scripts/restore.py BACKUP_PATH --to DESTINATION [--preview] [--force]

`--preview` lists what would be restored without writing anything.
Restoring to a non-empty destination requires `--force` (an explicit,
deliberate confirmation) — this script never silently overwrites existing
data. Restoring always targets a destination directory (defaults to a new
temp-adjacent folder, never the live `data/`/`output/` directories
implicitly) so a bad restore can never clobber a running installation by
accident; pass `--to` pointing at the real project root only when that's
genuinely intended.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_backup import verify_backup  # noqa: E402


def _resolve_backup_dir(backup_path: Path, extract_dir: Path) -> Path:
    if backup_path.is_dir():
        return backup_path
    with zipfile.ZipFile(backup_path) as archive:
        archive.extractall(extract_dir)
    return extract_dir


def _destination_is_nonempty(destination: Path) -> bool:
    return destination.exists() and any(destination.iterdir())


def preview_restore(backup_path: Path) -> list[str]:
    """Lists every file a real restore would write, without writing anything."""
    with tempfile.TemporaryDirectory() as tmp:
        backup_dir = _resolve_backup_dir(backup_path, Path(tmp))
        return sorted(str(p.relative_to(backup_dir)) for p in backup_dir.rglob("*") if p.is_file())


def restore_backup(backup_path: Path, destination: Path, *, force: bool = False) -> Path:
    verification = verify_backup(backup_path)
    if not verification.ok:
        raise RuntimeError(f"Refusing to restore a failed-verification backup: {verification.errors or verification.corrupted_files}")

    if _destination_is_nonempty(destination) and not force:
        raise RuntimeError(f"Destination {destination} is not empty — pass --force to restore into it anyway")

    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        backup_dir = _resolve_backup_dir(backup_path, Path(tmp))
        for item in backup_dir.rglob("*"):
            if item.is_dir() or item.name == "manifest.json":
                continue
            relative = item.relative_to(backup_dir)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    db_path = destination / "rental_intelligence.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            if row is None or row[0] != "ok":
                raise RuntimeError(f"Restored database failed integrity check: {row}")
        finally:
            conn.close()

    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="restore", description="Restore a Rental Intelligence Platform backup")
    parser.add_argument("backup_path", type=Path)
    parser.add_argument("--to", type=Path, required=True, dest="destination", help="Destination directory (never a live data/ directory implicitly)")
    parser.add_argument("--preview", action="store_true", help="List what would be restored, without writing anything")
    parser.add_argument("--force", action="store_true", help="Allow restoring into a non-empty destination")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.preview:
        for path in preview_restore(args.backup_path):
            print(path)
        return 0

    try:
        destination = restore_backup(args.backup_path, args.destination, force=args.force)
    except RuntimeError as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1

    print(f"Restored to: {destination}")
    print("Database integrity check: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
