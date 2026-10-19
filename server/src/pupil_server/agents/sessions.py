"""Live agent sessions, held in memory for the life of the sidecar."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from pupil_server.agents.base import AgentBackend, AgentConfig, AgentError, AgentEvent, AgentSession


class SessionNotFound(KeyError):
    pass


class SessionBusy(RuntimeError):
    """A turn is already running on this session."""


@dataclass
class _Entry:
    session: AgentSession
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionStore:
    def __init__(self, backend: AgentBackend) -> None:
        self.backend = backend
        self._entries: dict[str, _Entry] = {}

    async def open(self, config: AgentConfig) -> str:
        session = await self.backend.open_session(config)
        session_id = uuid.uuid4().hex
        self._entries[session_id] = _Entry(session)
        return session_id

    def _get(self, session_id: str) -> _Entry:
        try:
            return self._entries[session_id]
        except KeyError:
            raise SessionNotFound(session_id) from None

    def claim(self, session_id: str) -> _Entry:
        """Check the session exists and is idle, before a response is committed to."""
        entry = self._get(session_id)
        if entry.lock.locked():
            raise SessionBusy(session_id)
        return entry

    async def send(self, entry: _Entry, text: str) -> AsyncIterator[AgentEvent]:
        """Run one turn. Backend failures end the stream with an error event, not an exception."""
        async with entry.lock:
            try:
                async for event in entry.session.send(text):
                    yield event
            except Exception as exc:  # noqa: BLE001 - reported to the client as an event
                yield AgentError(message=f"{type(exc).__name__}: {exc}")

    async def close(self, session_id: str) -> None:
        entry = self._entries.pop(session_id, None)
        if entry is None:
            raise SessionNotFound(session_id)
        await entry.session.close()

    async def close_all(self) -> None:
        entries, self._entries = list(self._entries.values()), {}
        for entry in entries:
            await entry.session.close()
