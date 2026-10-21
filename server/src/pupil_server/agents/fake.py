"""A scripted backend for tests and offline development.

Each turn plays the next script entry. Tool calls really run the configured handlers, so the
tool plumbing is exercised even though no model is involved.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Sequence
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
    arguments: dict[str, Any] | Callable[[list[Any]], dict[str, Any]] = field(default_factory=dict)
    """Or a function of the outputs of the turn's earlier calls, for ids the app assigned."""


Step = Say | Call
Turn = Sequence[Step]


def _default_turn(text: str) -> Turn:
    return [Say(f"(fake agent) You said: {text}")]


class FakeSession:
    def __init__(self, config: AgentConfig, script: list[Turn]) -> None:
        self._tools = {t.name: t for t in config.tools}
        self._script = script
        self.received: list[str] = []
        self.closed = False

    async def send(self, text: str) -> AsyncIterator[AgentEvent]:
        self.received.append(text)
        turn = self._script.pop(0) if self._script else _default_turn(text)
        outputs: list[Any] = []
        for step in turn:
            if isinstance(step, Say):
                for word in step.text.split(" "):
                    yield TextDelta(text=word + " ")
                continue
            call_id = f"call_{uuid.uuid4().hex[:8]}"
            arguments = step.arguments(outputs) if callable(step.arguments) else step.arguments
            yield ToolCall(id=call_id, name=step.tool, input=arguments)
            tool = self._tools.get(step.tool)
            if tool is None:
                yield ToolResult(id=call_id, output=f"unknown tool {step.tool!r}", is_error=True)
            else:
                result = await tool.invoke(call_id, arguments)
                outputs.append(result.output)
                yield result
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

    async def open_session(self, config: AgentConfig) -> FakeSession:
        check_capabilities(self, config)
        # Sessions share the backend's script, so a test can script several runs in order.
        session = FakeSession(config, self._script)
        self.sessions.append(session)
        return session
