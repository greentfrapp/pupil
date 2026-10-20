"""Talks to the real Claude backend. Billed; run with `pytest -m live`."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from pupil_server.agents import AgentConfig, ToolCall, ToolResult, TurnComplete, tool
from pupil_server.agents.claude import ClaudeBackend
from pupil_server.app import create_app
from pupil_server.db import LOCAL_LEARNER, Database
from pupil_server.learning.tools import learning_tools
from pupil_server.settings import Settings

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
    # The lesson item union becomes a oneOf/$defs/$ref schema; check Claude takes it.
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
                "Create a syllabus on arithmetic with one unit, then a lesson for it with a "
                "teach card and one question of each type: multiple choice, true/false, numeric, "
                "text match, fill in the blank with a word bank, ordering and matching."
            )
        ]
    finally:
        await session.close()
        await db.close()

    calls = {e.id: e.name for e in events if isinstance(e, ToolCall)}
    succeeded = {calls[e.id] for e in events if isinstance(e, ToolResult) and not e.is_error}
    assert "create_lesson" in succeeded


def test_a_conversation_resumes_after_a_restart(tmp_path):
    # Two app instances on one database, as before and after a restart of the sidecar.
    def app():
        backend = ClaudeBackend(workdir=tmp_path / "agent")
        return create_app(Settings(), db_path=tmp_path / "pupil.db", agent_backend=backend)

    def say(client: TestClient, conversation_id: str, text: str) -> str:
        res = client.post(f"/api/conversations/{conversation_id}/messages", json={"text": text})
        events = [
            json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")
        ]
        assert events[-1]["type"] == "turn_complete", events[-1]
        return "".join(e["text"] for e in events if e["type"] == "text_delta")

    with TestClient(app()) as client:
        conversation_id = client.post("/api/conversations").json()["conversation_id"]
        say(client, conversation_id, "Please remember the word 'tangerine'. Just reply 'OK'.")

    with TestClient(app()) as client:
        reply = say(client, conversation_id, "Which word did I ask you to remember? One word.")

    assert "tangerine" in reply.lower()


def test_a_new_topic_gets_a_placement_lesson_from_a_run(tmp_path):
    backend = ClaudeBackend(workdir=tmp_path / "agent")
    app = create_app(Settings(), db_path=tmp_path / "pupil.db", agent_backend=backend)
    profile = {"why": "curiosity", "depth": "overview", "level": "basics"}
    with TestClient(app) as client:
        created = client.post("/api/topics", json={"request": "Fractions", "profile": profile})
        topic_id = created.json()["id"]
        client.portal.call(app.state.runs.wait, topic_id)
        topic = client.get(f"/api/topics/{topic_id}").json()

    assert topic["last_run"] == {"job": "placement", "state": "done", "error": None}
    [placement] = topic["lessons"]
    assert placement["purpose"] == "placement"
    assert placement["questions"] >= 5
