"""Connection management for the Rental Intelligence Platform's SQLite database.

Why this exists as its own module rather than each repository opening its own connection:
schema application (schema.sql) needs to happen exactly once per database file, in one place,
and every repository needs a connection configured the same way (foreign keys on, row_factory
set so query results come back as dict-like rows instead of plain tuples). Centralizing that
here means a repository never has to think about connection setup — it just asks for one.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.core.config import DB_PATH

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """Owns one SQLite database file. Construct one per process (or per test), then
    call `connect()` for a ready-to-use connection, or `transaction()` to get one that
    commits on success and rolls back on any exception.
    """

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._apply_schema()

    def _apply_schema(self) -> None:
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self.transaction() as conn:
            conn.executescript(schema_sql)

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
