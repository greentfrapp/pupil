"""A scripted backend for tests and offline development.

Each turn plays the next script entry. Tool calls really run the configured handlers, so the
tool plumbing is exercised even though no model is involved.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from pupil_server.agents.base import (
    AgentConfig,
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnComplete,
    check_capabilities,
)


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class Call:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


Step = Say | Call
Turn = Sequence[Step]


def _default_turn(text: str) -> Turn:
    return [Say(f"(fake agent) You said: {text}")]


class FakeSession:
    def __init__(self, config: AgentConfig, script: list[Turn], token: str) -> None:
        self._tools = {t.name: t for t in config.tools}
        self._script = script
        self._token = token
        self.received: list[str] = []
        self.closed = False

    @property
    def resume_token(self) -> str | None:
        return self._token

    async def send(self, text: str) -> AsyncIterator[AgentEvent]:
        self.received.append(text)
        turn = self._script.pop(0) if self._script else _default_turn(text)
        for step in turn:
            if isinstance(step, Say):
                for word in step.text.split(" "):
                    yield TextDelta(text=word + " ")
                continue
            call_id = f"call_{uuid.uuid4().hex[:8]}"
            yield ToolCall(id=call_id, name=step.tool, input=step.arguments)
            tool = self._tools.get(step.tool)
            if tool is None:
                yield ToolResult(id=call_id, output=f"unknown tool {step.tool!r}", is_error=True)
            else:
                yield await tool.invoke(call_id, step.arguments)
        yield TurnComplete(cost_usd=0.0)

    async def interrupt(self) -> None:
        pass

    async def close(self) -> None:
        self.closed = True


class FakeBackend:
    name = "fake"
    supports_web_search = True

    def __init__(self, script: Sequence[Turn] = ()) -> None:
        self._script = list(script)
        self.sessions: list[FakeSession] = []
        self.resumed: list[str] = []
        """The resume tokens sessions were opened with, in order."""

    async def open_session(self, config: AgentConfig, resume: str | None = None) -> FakeSession:
        check_capabilities(self, config)
        if resume:
            self.resumed.append(resume)
        # Sessions share the backend's script, so a test can script a whole conversation.
        session = FakeSession(config, self._script, resume or uuid.uuid4().hex)
        self.sessions.append(session)
        return session
