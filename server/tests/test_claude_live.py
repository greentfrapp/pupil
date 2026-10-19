"""Talks to the real Claude backend. Billed; run with `pytest -m live`."""

import pytest
from pydantic import BaseModel

from pupil_server.agents import AgentConfig, ToolCall, ToolResult, TurnComplete, tool
from pupil_server.agents.claude import ClaudeBackend

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
