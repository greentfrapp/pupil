"""Repository for topics and the notes the agent keeps about the learner for each.

Like the other repositories, every method takes the learner it acts for, and another
learner's topic is simply not found.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pupil_server.db.database import Database, NotFound, new_id, timestamp
from pupil_server.learning.topic import Note, Profile, Topic


class TopicRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, learner_id: str, request: str, profile: Profile) -> Topic:
        topic = Topic(
            id=new_id("top"), request=request, profile=profile, created_at=datetime.now(UTC)
        )

        def work(conn: sqlite3.Connection) -> Topic:
            conn.execute(
                "INSERT INTO topics (id, learner_id, request, profile, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    topic.id,
                    learner_id,
                    topic.request,
                    topic.profile.model_dump_json(),
                    timestamp(topic.created_at),
                ),
            )
            return topic

        return await self._db.run(work)

    async def get(self, learner_id: str, topic_id: str) -> Topic:
        return await self._db.run(lambda conn: topic_row(conn, learner_id, topic_id))

    async def list_recent(self, learner_id: str) -> list[Topic]:
        """The learner's topics, newest first."""

        def work(conn: sqlite3.Connection) -> list[Topic]:
            rows = conn.execute(
                f"{_TOPICS} WHERE learner_id = ? ORDER BY created_at DESC, rowid DESC",
                (learner_id,),
            )
            return [_topic(r) for r in rows]

        return await self._db.run(work)

    async def add_note(self, learner_id: str, topic_id: str, text: str) -> Note:
        note = Note(text=text, created_at=datetime.now(UTC))

        def work(conn: sqlite3.Connection) -> Note:
            topic_row(conn, learner_id, topic_id)
            conn.execute(
                "INSERT INTO notes (topic_id, text, created_at) VALUES (?, ?, ?)",
                (topic_id, note.text, timestamp(note.created_at)),
            )
            return note

        return await self._db.run(work)

    async def notes(self, learner_id: str, topic_id: str) -> list[Note]:
        """The topic's notes, oldest first."""

        def work(conn: sqlite3.Connection) -> list[Note]:
            topic_row(conn, learner_id, topic_id)
            rows = conn.execute(
                "SELECT text, created_at FROM notes WHERE topic_id = ? ORDER BY created_at, rowid",
                (topic_id,),
            )
            return [Note.model_validate(dict(r)) for r in rows]

        return await self._db.run(work)


_TOPICS = "SELECT id, request, profile, created_at FROM topics"


def _topic(row: sqlite3.Row) -> Topic:
    return Topic(
        id=row["id"],
        request=row["request"],
        profile=Profile.model_validate_json(row["profile"]),
        created_at=row["created_at"],
    )


def topic_row(conn: sqlite3.Connection, learner_id: str, topic_id: str) -> Topic:
    """The learner's topic, for other repositories to check it exists and is theirs."""
    row = conn.execute(
        f"{_TOPICS} WHERE learner_id = ? AND id = ?", (learner_id, topic_id)
    ).fetchone()
    if row is None:
        raise NotFound(f"no topic {topic_id!r}")
    return _topic(row)
