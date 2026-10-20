"""Conversations that outlive the agent sessions serving them.

A conversation is saved; its agent session lives only in memory. When a message arrives for a
conversation with no live session (after a restart, or after the client let it go), a session
is reopened from the latest resume token, so the agent remembers the conversation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable

import anyio

from pupil_server.agents.base import AgentConfig, AgentEvent, TextDelta, ToolCall
from pupil_server.agents.sessions import Entry, SessionStore
from pupil_server.conversations.transcript import Conversation, Prompt, TranscriptItem
from pupil_server.db.conversations import ConversationRepo

log = logging.getLogger(__name__)


class Conversations:
    def __init__(
        self,
        sessions: SessionStore,
        repo: ConversationRepo,
        config: Callable[[str], AgentConfig],
    ) -> None:
        self._sessions = sessions
        self._repo = repo
        self._config = config  # the agent config for a learner's conversations
        self._opening = asyncio.Lock()

    async def start(self, learner_id: str) -> Conversation:
        """A new conversation. Its session opens with the first message."""
        return await self._repo.create(learner_id)

    async def list_recent(self, learner_id: str) -> list[Conversation]:
        return await self._repo.list_recent(learner_id)

    async def get(self, learner_id: str, conversation_id: str) -> Conversation:
        return await self._repo.get(learner_id, conversation_id)

    async def transcript(self, learner_id: str, conversation_id: str) -> list[TranscriptItem]:
        return await self._repo.transcript(learner_id, conversation_id)

    async def claim(self, learner_id: str, conversation_id: str) -> Entry:
        """The conversation's session, idle and ready for a turn, reopened if it wasn't live."""
        await self._repo.get(learner_id, conversation_id)  # someone else's is not found
        # One at a time, so two messages arriving together can't open two sessions.
        async with self._opening:
            if not self._sessions.is_open(conversation_id):
                await self._open(learner_id, conversation_id)
        return self._sessions.claim(conversation_id)

    async def _open(self, learner_id: str, conversation_id: str) -> None:
        config = self._config(learner_id)
        backend = self._sessions.backend.name
        token = await self._repo.resume_token(learner_id, conversation_id, backend)
        if token is None:
            await self._sessions.open(conversation_id, config)
            return
        try:
            await self._sessions.open(conversation_id, config, resume=token)
        except Exception:
            # The backend may have lost the session, e.g. its files were deleted. Carry on
            # without the agent's memory of it, rather than leave the conversation stuck.
            log.warning(
                "could not resume conversation %s; starting a new agent session",
                conversation_id,
                exc_info=True,
            )
            await self._sessions.open(conversation_id, config)

    async def send(
        self, learner_id: str, conversation_id: str, entry: Entry, prompt: Prompt
    ) -> AsyncIterator[AgentEvent]:
        """Run one turn, saving it to the transcript as it goes.

        Arguments of tools that hide their input (a lesson's answer key) are left out of both
        the stream and the transcript.
        """
        hidden = {t.name for t in self._config(learner_id).tools if t.hide_input}
        await self._repo.append(learner_id, conversation_id, prompt)
        text_run: list[str] = []

        async def save_text() -> None:
            if text_run:
                merged = TextDelta(text="".join(text_run))
                text_run.clear()
                await self._repo.append(learner_id, conversation_id, merged)

        try:
            async for event in self._sessions.send(entry, prompt.text):
                if isinstance(event, ToolCall) and event.name in hidden:
                    event = event.model_copy(update={"input": {}})
                if isinstance(event, TextDelta):
                    text_run.append(event.text)
                else:
                    await save_text()
                    await self._repo.append(learner_id, conversation_id, event)
                yield event
        finally:
            # Also when the client goes away mid-turn, which cancels the stream: keep what
            # was said, and the token to carry on from.
            with anyio.CancelScope(shield=True):
                await save_text()
                token = entry.session.resume_token
                if token:
                    backend = self._sessions.backend.name
                    await self._repo.save_resume_token(learner_id, conversation_id, backend, token)

    async def release(self, learner_id: str, conversation_id: str) -> None:
        """Close the live session, if there is one; the conversation can carry on later."""
        await self._repo.get(learner_id, conversation_id)
        if self._sessions.is_open(conversation_id):
            await self._sessions.close(conversation_id)
