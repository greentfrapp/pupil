"""The contract between Pupil and whatever agent runtime does the work.

Nothing here imports a vendor SDK. The app builds an `AgentConfig`, opens an `AgentSession`
on some `AgentBackend`, and reads `AgentEvent`s back; each backend adapts its runtime to that.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ToolOutput = str | dict[str, Any]


@dataclass(frozen=True)
class Tool:
    """A function the agent may call, with its arguments described by a pydantic model."""

    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any], Awaitable[ToolOutput]]

    def json_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    async def invoke(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        """Validate the agent's arguments and run the handler; failures become error results."""
        try:
            parsed = self.input_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult(id=call_id, output=f"invalid arguments: {exc}", is_error=True)
        try:
            output = await self.handler(parsed)
        except Exception as exc:  # noqa: BLE001 - the agent sees the failure, not the app
            return ToolResult(id=call_id, output=f"{type(exc).__name__}: {exc}", is_error=True)
        return ToolResult(id=call_id, output=output)


def tool(name: str, description: str) -> Callable[[Callable[..., Awaitable[ToolOutput]]], Tool]:
    """Make a `Tool` from an async handler whose single parameter is a pydantic model."""

    def wrap(handler: Callable[..., Awaitable[ToolOutput]]) -> Tool:
        params = list(inspect.signature(handler).parameters)
        hints = get_type_hints(handler)
        model = hints.get(params[0]) if len(params) == 1 else None
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise TypeError(f"tool {name!r}: handler must take one pydantic model argument")
        return Tool(name=name, description=description, input_model=model, handler=handler)

    return wrap


class AgentConfig(BaseModel):
    """What the app asks of an agent, independent of who runs it."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    system_prompt: str
    tools: list[Tool] = Field(default_factory=list)
    web_search: bool = False
    """Let the agent search and fetch the web, using the backend's own implementation."""
    model: str | None = None
    """Backend-specific model name; None uses the backend's default."""
    max_turns: int | None = None


# Events. Tool names are always the app's own (`web_search`/`web_fetch` for the built-ins),
# never a backend's internal naming.


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    input: dict[str, Any]


class ToolResult(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    id: str
    output: ToolOutput | list[Any] | None
    is_error: bool = False

    def text(self) -> str:
        """The output as the text an agent reads back: as is, or as JSON."""
        return self.output if isinstance(self.output, str) else json.dumps(self.output)


class TurnComplete(BaseModel):
    type: Literal["turn_complete"] = "turn_complete"
    cost_usd: float | None = None
    usage: dict[str, Any] | None = None


class AgentError(BaseModel):
    type: Literal["error"] = "error"
    message: str


AgentEvent = Annotated[
    TextDelta | ToolCall | ToolResult | TurnComplete | AgentError, Field(discriminator="type")
]


class UnsupportedCapability(RuntimeError):
    """The backend cannot provide something the config asked for."""


class AgentSession(Protocol):
    """One session with the agent. It keeps its own history between turns."""

    def send(self, text: str) -> AsyncIterator[AgentEvent]:
        """Run one turn; the last event is `TurnComplete` or `AgentError`."""
        ...

    async def interrupt(self) -> None: ...

    async def close(self) -> None: ...


class AgentBackend(Protocol):
    name: str
    supports_web_search: bool

    async def open_session(self, config: AgentConfig) -> AgentSession: ...


def check_capabilities(backend: AgentBackend, config: AgentConfig) -> None:
    if config.web_search and not backend.supports_web_search:
        raise UnsupportedCapability(f"{backend.name} backend has no web search")
