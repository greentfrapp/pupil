"""The SQLite database: one connection, numbered migrations, and transactions off the event loop.

Records are append-only. A change is a new row (a syllabus revision, an attempt), never an
update, so history is never lost. Whole documents are stored as pydantic JSON in `body` columns;
anything queried item by item gets its own table.
"""

from __future__ import annotations

import asyncio
import secrets
import sqlite3
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

LOCAL_LEARNER = "lrn_local"
"""The one learner of a local install. Every record names its learner, ready for accounts."""

Migration = tuple[int, str]
"""A schema version and the SQL that brings the database up to it."""


class DatabaseTooNew(RuntimeError):
    """The database was migrated by a newer Pupil than this one."""


class NotFound(LookupError):
    """No record with that id belongs to the learner."""


class AlreadyExists(ValueError):
    """A record with that id is already stored; records are never overwritten."""


def new_id(prefix: str) -> str:
    """A random id that says what it names, e.g. `syl_3f9c...`."""
    return f"{prefix}_{secrets.token_hex(8)}"


def timestamp(at: datetime) -> str:
    """ISO 8601 in UTC, so stored timestamps sort as text."""
    if at.tzinfo is None:
        raise ValueError(f"timestamp {at} has no timezone")
    return at.astimezone(UTC).isoformat()


class Database:
    """One connection, used only from its own worker thread.

    Calls run one at a time in the order made, and never overlap, even when the task awaiting
    one is cancelled and the work carries on in the thread.
    """

    def __init__(self, executor: ThreadPoolExecutor, conn: sqlite3.Connection) -> None:
        self._executor = executor
        self._conn = conn

    @classmethod
    async def open(cls, path: Path) -> Database:
        """Connect, migrate to the latest schema and make sure the local learner exists."""
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pupil-db")
        try:
            conn = await asyncio.get_running_loop().run_in_executor(executor, _connect, path)
        except BaseException:
            executor.shutdown()
            raise
        return cls(executor, conn)

    async def run[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run `work` in one transaction, committed unless `work` raises."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _transaction, self._conn, work)

    async def close(self) -> None:
        await asyncio.get_running_loop().run_in_executor(self._executor, self._conn.close)
        self._executor.shutdown()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Transactions are begun explicitly, rather than by the sqlite3 module's guesswork.
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        migrate(conn)
        conn.execute(
            "INSERT OR IGNORE INTO learners (id, created_at) VALUES (?, ?)",
            (LOCAL_LEARNER, timestamp(datetime.now(UTC))),
        )
    except BaseException:
        conn.close()
        raise
    return conn


def _transaction[T](conn: sqlite3.Connection, work: Callable[[sqlite3.Connection], T]) -> T:
    conn.execute("BEGIN IMMEDIATE")
    try:
        result = work(conn)
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    return result


def load_migrations(directory: Traversable | None = None) -> list[Migration]:
    """Read `NNNN_name.sql` files, which must be numbered from 1 with no gaps."""
    directory = directory or resources.files(__package__) / "migrations"
    found = sorted(
        (int(f.name.split("_", 1)[0]), f.read_text(encoding="utf-8"))
        for f in directory.iterdir()
        if f.name.endswith(".sql")
    )
    versions = [v for v, _ in found]
    if versions != list(range(1, len(found) + 1)):
        raise RuntimeError(f"migrations must be numbered 1 to n with no gaps, found {versions}")
    return found


def migrate(conn: sqlite3.Connection, migrations: Iterable[Migration] | None = None) -> None:
    """Apply each migration newer than the database's `user_version`, each in its own transaction."""
    migrations = list(load_migrations() if migrations is None else migrations)
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > len(migrations):
        raise DatabaseTooNew(
            f"the database is at schema version {current}, but this Pupil only knows up to "
            f"{len(migrations)}. Update Pupil, or set PUPIL_DB_PATH to use a different database."
        )
    for version, sql in migrations[current:]:
        try:
            conn.executescript(
                f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;"
            )
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
