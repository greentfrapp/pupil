"""Talks to the real Claude backend. Billed; run with `pytest -m live`."""

import pytest
from pydantic import BaseModel

from pupil_server.agents import AgentConfig, ToolCall, ToolResult, TurnComplete, tool
from pupil_server.agents.claude import ClaudeBackend
from pupil_server.db import LOCAL_LEARNER, Database
from pupil_server.learning.tools import learning_tools

pytestmark = pytest.mark.live


class SecretArgs(BaseModel):
    pass


@tool("get_secret_word", "Return today's secret word.")
async def get_secret_word(_: SecretArgs) -> str:
    return "marmalade"


async def test_one_turn_with_a_tool_call(tmp_path):
    backend = ClaudeBackend(workdir=tmp_path)
    config = AgentConfig(
        system_prompt="Answer briefly. Use tools when asked.",
        tools=[get_secret_word],
        max_turns=4,
    )
    session = await backend.open_session(config)
    try:
        events = [e async for e in session.send("Use your tool to get the secret word.")]
    finally:
        await session.close()

    assert any(isinstance(e, ToolCall) and e.name == "get_secret_word" for e in events)
    assert any(isinstance(e, ToolResult) and e.output == "marmalade" for e in events)
    assert isinstance(events[-1], TurnComplete)
    assert session.resume_token


async def test_claude_can_fill_in_the_learning_tool_schemas(tmp_path):
    # The question and response unions become oneOf/$defs/$ref schemas; check Claude takes them.
    db = await Database.open(tmp_path / "pupil.db")
    session = await ClaudeBackend(workdir=tmp_path).open_session(
        AgentConfig(
            system_prompt="You test tools. Do exactly what you are asked, then reply 'done'.",
            tools=learning_tools(db, LOCAL_LEARNER),
            max_turns=8,
        )
    )
    try:
        events = [
            e
            async for e in session.send(
                "Create a placement quiz on arithmetic with one multiple choice question, one "
                "true/false question, one numeric question and one text match question. Then "
                "submit these answers for it: the first option, true, 42 and 'seven'."
            )
        ]
    finally:
        await session.close()
        await db.close()

    calls = {e.id: e.name for e in events if isinstance(e, ToolCall)}
    succeeded = {calls[e.id] for e in events if isinstance(e, ToolResult) and not e.is_error}
    assert "create_quiz" in succeeded
    assert "submit_quiz_answers" in succeeded
