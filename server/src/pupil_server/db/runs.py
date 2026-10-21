"""Repository for the agent's runs: what each was for, how it ended, and its log.

A run's start and end are separate rows, so nothing is ever updated; a run with no end was
cut off, e.g. by a restart.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, TypeAdapter

from pupil_server.conversations.transcript import TranscriptItem
from pupil_server.db.database import Database, NotFound, new_id, timestamp
from pupil_server.db.topics import topic_row

_ITEM: TypeAdapter[TranscriptItem] = TypeAdapter(TranscriptItem)


class Run(BaseModel):
    id: str
    topic_id: str
    job: str
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    """None while the run goes on, or if it was cut off."""
    error: str | None = None
    """Why the run didn't do its job; None if it did, or hasn't finished."""
    cost_usd: float | None = None

    @property
    def succeeded(self) -> bool:
        return self.finished_at is not None and self.error is None


class RunRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def start(self, learner_id: str, topic_id: str, job: str) -> Run:
        run = Run(id=new_id("run"), topic_id=topic_id, job=job, started_at=datetime.now(UTC))

        def work(conn: sqlite3.Connection) -> Run:
            topic_row(conn, learner_id, topic_id)
            conn.execute(
                "INSERT INTO runs (id, learner_id, topic_id, job, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (run.id, learner_id, topic_id, job, timestamp(run.started_at)),
            )
            return run

        return await self._db.run(work)

    async def append(self, learner_id: str, run_id: str, item: TranscriptItem) -> None:
        """Add an item to the end of the run's log."""

        def work(conn: sqlite3.Connection) -> None:
            _run(conn, learner_id, run_id)
            conn.execute(
                "INSERT INTO run_items (run_id, seq, at, body) "
                "SELECT ?, coalesce(max(seq), 0) + 1, ?, ? FROM run_items WHERE run_id = ?",
                (run_id, _now(), item.model_dump_json(), run_id),
            )

        await self._db.run(work)

    async def finish(
        self, learner_id: str, run_id: str, error: str | None, cost_usd: float | None
    ) -> None:
        def work(conn: sqlite3.Connection) -> None:
            _run(conn, learner_id, run_id)
            conn.execute(
                "INSERT INTO run_ends (run_id, finished_at, error, cost_usd) VALUES (?, ?, ?, ?)",
                (run_id, _now(), error, cost_usd),
            )

        await self._db.run(work)

    async def get(self, learner_id: str, run_id: str) -> Run:
        return await self._db.run(lambda conn: _run(conn, learner_id, run_id))

    async def log(self, learner_id: str, run_id: str) -> list[TranscriptItem]:
        def work(conn: sqlite3.Connection) -> list[TranscriptItem]:
            _run(conn, learner_id, run_id)
            rows = conn.execute(
                "SELECT body FROM run_items WHERE run_id = ? ORDER BY seq", (run_id,)
            )
            return [_ITEM.validate_json(r["body"]) for r in rows]

        return await self._db.run(work)

    async def latest(self, learner_id: str, topic_id: str) -> Run | None:
        """The topic's most recent run, however it ended."""
        return await self._db.run(lambda conn: _latest(conn, learner_id, topic_id, ""))

    async def latest_success(self, learner_id: str, topic_id: str) -> Run | None:
        """The topic's most recent run that did its job."""

        def work(conn: sqlite3.Connection) -> Run | None:
            succeeded = " AND e.finished_at IS NOT NULL AND e.error IS NULL"
            return _latest(conn, learner_id, topic_id, succeeded)

        return await self._db.run(work)


def _now() -> str:
    return timestamp(datetime.now(UTC))


_RUNS = (
    "SELECT r.id, r.topic_id, r.job, r.started_at, e.finished_at, e.error, e.cost_usd "
    "FROM runs AS r LEFT JOIN run_ends AS e ON e.run_id = r.id"
)


def _run(conn: sqlite3.Connection, learner_id: str, run_id: str) -> Run:
    row = conn.execute(f"{_RUNS} WHERE r.learner_id = ? AND r.id = ?", (learner_id, run_id))
    found = row.fetchone()
    if found is None:
        raise NotFound(f"no run {run_id!r}")
    return Run.model_validate(dict(found))


def _latest(conn: sqlite3.Connection, learner_id: str, topic_id: str, where: str) -> Run | None:
    topic_row(conn, learner_id, topic_id)
    row = conn.execute(
        f"{_RUNS} WHERE r.topic_id = ?{where} ORDER BY r.started_at DESC, r.rowid DESC LIMIT 1",
        (topic_id,),
    ).fetchone()
    return None if row is None else Run.model_validate(dict(row))
