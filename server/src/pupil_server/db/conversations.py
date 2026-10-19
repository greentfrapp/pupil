"""Repository for conversations: their transcripts and resume tokens.

Like the learning repositories, every method takes the learner it acts for, and another
learner's conversation is simply not found.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pydantic import TypeAdapter

from pupil_server.conversations.transcript import Conversation, TranscriptItem
from pupil_server.db.database import Database, NotFound, new_id, timestamp

_ITEM: TypeAdapter[TranscriptItem] = TypeAdapter(TranscriptItem)


class ConversationRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, learner_id: str) -> Conversation:
        conversation = Conversation(id=new_id("conv"), created_at=datetime.now(UTC))

        def work(conn: sqlite3.Connection) -> Conversation:
            conn.execute(
                "INSERT INTO conversations (id, learner_id, created_at) VALUES (?, ?, ?)",
                (conversation.id, learner_id, timestamp(conversation.created_at)),
            )
            return conversation

        return await self._db.run(work)

    async def get(self, learner_id: str, conversation_id: str) -> Conversation:
        return await self._db.run(lambda conn: _conversation(conn, learner_id, conversation_id))

    async def list_recent(self, learner_id: str) -> list[Conversation]:
        """The learner's conversations, newest first."""

        def work(conn: sqlite3.Connection) -> list[Conversation]:
            rows = conn.execute(
                "SELECT id, created_at FROM conversations WHERE learner_id = ? "
                "ORDER BY created_at DESC, rowid DESC",
                (learner_id,),
            )
            return [Conversation.model_validate(dict(r)) for r in rows]

        return await self._db.run(work)

    async def append(self, learner_id: str, conversation_id: str, item: TranscriptItem) -> None:
        """Add an item to the end of the transcript."""

        def work(conn: sqlite3.Connection) -> None:
            _conversation(conn, learner_id, conversation_id)
            conn.execute(
                "INSERT INTO transcript_items (conversation_id, seq, at, body) "
                "SELECT ?, coalesce(max(seq), 0) + 1, ?, ? FROM transcript_items "
                "WHERE conversation_id = ?",
                (conversation_id, _now(), item.model_dump_json(), conversation_id),
            )

        await self._db.run(work)

    async def transcript(self, learner_id: str, conversation_id: str) -> list[TranscriptItem]:
        def work(conn: sqlite3.Connection) -> list[TranscriptItem]:
            _conversation(conn, learner_id, conversation_id)
            rows = conn.execute(
                "SELECT body FROM transcript_items WHERE conversation_id = ? ORDER BY seq",
                (conversation_id,),
            )
            return [_ITEM.validate_json(r["body"]) for r in rows]

        return await self._db.run(work)

    async def save_resume_token(
        self, learner_id: str, conversation_id: str, backend: str, token: str
    ) -> None:
        """Record the token, unless it is already the latest for this backend."""

        def work(conn: sqlite3.Connection) -> None:
            _conversation(conn, learner_id, conversation_id)
            if _resume_token(conn, conversation_id, backend) == token:
                return
            conn.execute(
                "INSERT INTO resume_tokens (conversation_id, backend, token, at) "
                "VALUES (?, ?, ?, ?)",
                (conversation_id, backend, token, _now()),
            )

        await self._db.run(work)

    async def resume_token(self, learner_id: str, conversation_id: str, backend: str) -> str | None:
        """The latest token from this backend, if it has served the conversation before."""

        def work(conn: sqlite3.Connection) -> str | None:
            _conversation(conn, learner_id, conversation_id)
            return _resume_token(conn, conversation_id, backend)

        return await self._db.run(work)


def _now() -> str:
    return timestamp(datetime.now(UTC))


def _conversation(conn: sqlite3.Connection, learner_id: str, conversation_id: str) -> Conversation:
    row = conn.execute(
        "SELECT id, created_at FROM conversations WHERE learner_id = ? AND id = ?",
        (learner_id, conversation_id),
    ).fetchone()
    if row is None:
        raise NotFound(f"no conversation {conversation_id!r}")
    return Conversation.model_validate(dict(row))


def _resume_token(conn: sqlite3.Connection, conversation_id: str, backend: str) -> str | None:
    row = conn.execute(
        "SELECT token FROM resume_tokens WHERE conversation_id = ? AND backend = ? "
        "ORDER BY rowid DESC LIMIT 1",
        (conversation_id, backend),
    ).fetchone()
    return row["token"] if row else None
