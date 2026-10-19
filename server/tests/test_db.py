import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pupil_server.agents.fake import FakeBackend
from pupil_server.app import create_app
from pupil_server.db import LOCAL_LEARNER, Database, DatabaseTooNew
from pupil_server.db.database import load_migrations, migrate, timestamp
from pupil_server.settings import Settings


def user_version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


async def test_open_migrates_and_seeds_the_local_learner(tmp_path: Path):
    path = tmp_path / "pupil.db"
    for _ in range(2):  # reopening must not migrate or seed twice
        db = await Database.open(path)
        learners = await db.run(lambda c: [r["id"] for r in c.execute("SELECT id FROM learners")])
        await db.close()
        assert learners == [LOCAL_LEARNER]
    assert user_version(path) == len(load_migrations())


async def test_run_rolls_back_when_the_work_fails(tmp_path: Path):
    db = await Database.open(tmp_path / "pupil.db")

    def add_then_fail(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO learners (id, created_at) VALUES ('lrn_2', 'now')")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await db.run(add_then_fail)
    count = await db.run(lambda c: c.execute("SELECT count(*) FROM learners").fetchone()[0])
    await db.close()
    assert count == 1


def test_a_failed_migration_leaves_the_previous_version():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    migrations = [(1, "CREATE TABLE a (x);"), (2, "CREATE TABLE b (x);\nSELECT * FROM nowhere;")]
    with pytest.raises(sqlite3.OperationalError, match="no such table: nowhere"):
        migrate(conn, migrations)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"a"}


def test_a_newer_database_is_refused():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("PRAGMA user_version = 2")
    with pytest.raises(DatabaseTooNew, match="schema version 2, but this Pupil only knows up to 1"):
        migrate(conn, [(1, "CREATE TABLE a (x);")])


def test_migrations_must_be_numbered_without_gaps(tmp_path: Path):
    (tmp_path / "0001_first.sql").write_text("")
    (tmp_path / "0003_third.sql").write_text("")
    with pytest.raises(RuntimeError, match=r"found \[1, 3\]"):
        load_migrations(tmp_path)


def test_timestamps_are_utc_and_need_a_timezone():
    at = datetime(2026, 1, 2, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    assert timestamp(at) == "2026-01-02T01:30:00+00:00"
    with pytest.raises(ValueError, match="has no timezone"):
        timestamp(datetime(2026, 1, 2))


def test_app_opens_the_database_at_startup(tmp_path: Path):
    path = tmp_path / "pupil.db"
    app = create_app(Settings(), db_path=path, agent_backend=FakeBackend([]))
    with TestClient(app):
        assert isinstance(app.state.db, Database)
    assert user_version(path) == len(load_migrations())
