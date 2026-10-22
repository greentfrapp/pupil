"""What a run's log holds: its brief, then the agent's events.

Events are kept as they were streamed, except that each stretch of streamed text is stored as
one `text_delta`. Logs are for debugging and tracking cost, never replayed to the agent.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pupil_server.agents.base import AgentError, TextDelta, ToolCall, ToolResult, TurnComplete


class UserMessage(BaseModel):
    """What the run was sent: its brief."""

    type: Literal["user_message"] = "user_message"
    text: str


LogItem = Annotated[
    UserMessage | TextDelta | ToolCall | ToolResult | TurnComplete | AgentError,
    Field(discriminator="type"),
]
