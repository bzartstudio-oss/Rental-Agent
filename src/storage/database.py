"""Connection management for the Rental Intelligence Platform's SQLite database.

Why this exists as its own module rather than each repository opening its own connection:
schema application (schema.sql) needs to happen exactly once per database file, in one place,
and every repository needs a connection configured the same way (foreign keys on, row_factory
set so query results come back as dict-like rows instead of plain tuples). Centralizing that
here means a repository never has to think about connection setup — it just asks for one.

Also owns the migration runner (docs/10_Roadmap.md "Migration Plan") — schema.sql covers
the tables that exist unconditionally; everything added after that ships as a numbered
file under storage/migrations/, applied automatically here.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from src.core.config import DB_PATH

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_FILENAME_RE = re.compile(r"^(\d+)_")


class Database:
    """Owns one SQLite database file. Construct one per process (or per test), then
    call `connect()` for a ready-to-use connection, or `transaction()` to get one that
    commits on success and rolls back on any exception.
    """

    def __init__(self, db_path: Path | str = DB_PATH, migrations_dir: Path | str = _MIGRATIONS_DIR) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrations_dir = Path(migrations_dir)
        self._apply_schema()
        self._apply_migrations()

    def _apply_schema(self) -> None:
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self.transaction() as conn:
            conn.executescript(schema_sql)

    def _apply_migrations(self) -> None:
        """Discovers every `NNNN_*.sql` file under `migrations_dir`, applies whichever
        ones haven't run yet (per `schema_migrations`), in ascending version order, each
        in its own transaction. A migration that raises is fully rolled back (see
        `_apply_one_migration` for why `executescript` isn't used here) and its exception
        propagates — a failed migration stops startup rather than leaving the database in
        a half-migrated state silently.
        """
        if not self.migrations_dir.exists():
            return

        applied = self._applied_migration_versions()

        for version, path in self._discover_migrations():
            if version in applied:
                continue
            self._apply_one_migration(version, path)

    def _discover_migrations(self) -> list[tuple[int, Path]]:
        """Returns (version, path) pairs sorted by version — ascending numeric order,
        not filesystem/alphabetical order, so `0002_*.sql` never runs before `0010_*.sql`
        just because "10" sorts before "2" as text.
        """
        migrations = []
        for path in self.migrations_dir.glob("*.sql"):
            match = _MIGRATION_FILENAME_RE.match(path.name)
            if not match:
                raise ValueError(
                    f"Migration file {path.name!r} doesn't start with a numeric version "
                    "(expected e.g. '0001_description.sql') — refusing to guess its order"
                )
            migrations.append((int(match.group(1)), path))

        migrations.sort(key=lambda pair: pair[0])
        return migrations

    def _applied_migration_versions(self) -> set[int]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {row["version"] for row in rows}

    def _apply_one_migration(self, version: int, path: Path) -> None:
        """Executes every statement in `path` and records the version as applied, all in
        one transaction. Deliberately does NOT use `conn.executescript()` — Python's
        sqlite3 doesn't guarantee it runs as a single atomic unit (it implicitly commits
        any pending transaction first and applies no transaction control of its own), so
        a script that fails partway through could leave earlier statements committed with
        no way to roll them back. Executing each statement individually is the fix for
        that — but it introduces a second, less obvious problem: Python's `sqlite3`
        module only *implicitly* opens a transaction before DML statements (INSERT/
        UPDATE/DELETE) under the legacy `isolation_level` default; DDL statements
        (CREATE TABLE, ALTER TABLE) are **not** included in that heuristic and commit
        immediately regardless of the `self.transaction()` wrapper — so `rollback()`
        would silently do nothing for exactly the statements a migration is mostly made
        of. SQLite itself fully supports transactional DDL; getting Python's driver to
        actually use that requires bypassing its implicit-transaction guessing entirely
        with an explicit `BEGIN`/`COMMIT`/`ROLLBACK`, which is what this method does
        (using its own connection with `isolation_level = None`, not `self.transaction()`).
        """
        sql = path.read_text(encoding="utf-8")
        statements = _split_statements(sql)

        conn = sqlite3.connect(self.db_path)
        conn.isolation_level = None  # hand transaction control entirely to the explicit
        conn.row_factory = sqlite3.Row  # BEGIN/COMMIT/ROLLBACK below — see docstring
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("BEGIN")
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def connect(self) -> sqlite3.Connection:
        """A single connection, configured consistently. Callers are responsible for
        closing it (or use `transaction()` below, which does that for you).
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Use for any write: `with db.transaction() as conn: conn.execute(...)`.
        Commits if the block completes normally, rolls back if it raises — so a
        partially-written multi-statement change (e.g. an apartment update plus its
        history row) never lands half-done.
        """
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _split_statements(sql: str) -> list[str]:
    """Splits a migration file into individual statements on `;`. Simple, not a real SQL
    parser — safe here because migrations are controlled DDL-only files with no
    semicolons inside string literals. Line comments (`-- ...`) are stripped *before*
    splitting, not after: a `--` comment can contain a semicolon as ordinary English
    punctuation (e.g. "see database.py; it does X"), which would otherwise be
    misread as a statement boundary — stripping first means only semicolons in real SQL
    ever count.
    """
    without_comments = _strip_line_comments(sql)
    return [fragment.strip() for fragment in without_comments.split(";") if fragment.strip()]


def _strip_line_comments(sql: str) -> str:
    """Removes everything from `--` to end of line, for every line. Doesn't understand
    string literals (a `--` inside a quoted string would be wrongly treated as a comment
    start) — not a concern for this project's migrations, which are plain DDL with no
    string literals containing `--`.
    """
    lines = []
    for line in sql.splitlines():
        comment_start = line.find("--")
        lines.append(line[:comment_start] if comment_start != -1 else line)
    return "\n".join(lines)
