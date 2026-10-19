"""What a conversation's transcript holds.

The learner's messages, and the agent's events as they were streamed, except that each run of
streamed text is stored as one `text_delta`. A client can therefore replay a transcript through
the same code that renders a live turn.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field

from pupil_server.agents.base import AgentError, TextDelta, ToolCall, ToolResult, TurnComplete


class UserMessage(BaseModel):
    type: Literal["user_message"] = "user_message"
    text: str


class QuizResults(BaseModel):
    """A finished quiz, reported to the agent by the app rather than typed by the learner."""

    type: Literal["quiz_results"] = "quiz_results"
    quiz_id: str
    attempt_id: str
    correct: int
    total: int
    text: str
    """What the agent was told."""


Prompt = UserMessage | QuizResults
"""What starts a turn."""

TranscriptItem = Annotated[
    UserMessage | QuizResults | TextDelta | ToolCall | ToolResult | TurnComplete | AgentError,
    Field(discriminator="type"),
]


class Conversation(BaseModel):
    id: str
    created_at: AwareDatetime
