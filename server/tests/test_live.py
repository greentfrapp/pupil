"""Talks to the real agent backends, each test against each. Billed; run with `pytest -m live`."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from pupil_server.agents import AgentConfig, ToolCall, ToolResult, TurnComplete, tool
from pupil_server.agents.claude import ClaudeBackend
from pupil_server.agents.codex import CodexBackend
from pupil_server.app import create_app
from pupil_server.db import LOCAL_LEARNER, Database
from pupil_server.db.learning import AttemptRepo, LessonRepo, SyllabusRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.lesson import Answer, Attempt, BoolResponse, Lesson, TrueFalse
from pupil_server.learning.syllabus import Objective, Syllabus, Unit
from pupil_server.learning.tools import learning_tools
from pupil_server.learning.topic import Profile
from pupil_server.settings import Settings

pytestmark = pytest.mark.live

BACKENDS = {"claude": ClaudeBackend, "codex": CodexBackend}


@pytest.fixture(params=list(BACKENDS))
def backend_name(request) -> str:
    return request.param


@pytest.fixture
async def backend(backend_name, tmp_path):
    """For tests that open sessions themselves; an app closes its own backend."""
    backend = BACKENDS[backend_name](workdir=tmp_path / "agent")
    yield backend
    await backend.close()


class SecretArgs(BaseModel):
    pass


@tool("get_secret_word", "Return today's secret word.")
async def get_secret_word(_: SecretArgs) -> str:
    return "marmalade"


async def test_one_turn_with_a_tool_call(backend):
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
    assert events[-1].model  # Pupil's default model was taken, and the turn names it
    print(f"{backend.name}: {events[-1].model}")


async def test_the_agent_can_fill_in_the_learning_tool_schemas(backend, tmp_path):
    # The lesson item union becomes a oneOf/$defs/$ref schema, large enough for Codex to
    # compact it; check the agent can still fill it in.
    db = await Database.open(tmp_path / "pupil.db")
    profile = Profile(why="curiosity", depth="overview", level="new")
    topic = await TopicRepo(db).create(LOCAL_LEARNER, "Arithmetic", profile)
    session = await backend.open_session(
        AgentConfig(
            system_prompt="You test tools. Do exactly what you are asked, then reply 'done'.",
            tools=learning_tools(db, LOCAL_LEARNER, topic.id),
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


def test_a_new_topic_gets_a_placement_lesson_from_a_run(backend_name, tmp_path):
    app = app_on(backend_name, tmp_path)
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


def app_on(backend_name: str, tmp_path):
    backend = BACKENDS[backend_name](workdir=tmp_path / "agent")
    return create_app(Settings(), db_path=tmp_path / "pupil.db", agent_backend=backend)


def settle(client: TestClient, topic_id: str) -> dict:
    client.portal.call(client.app.state.runs.wait, topic_id)
    return client.get(f"/api/topics/{topic_id}").json()


def test_a_plan_run_lays_out_the_path_and_the_next_lesson_is_written_ahead(backend_name, tmp_path):
    # New to the topic, so no placement: the plan run, then a run writing the second lesson.
    profile = {"why": "work", "depth": "working", "level": "new"}
    with TestClient(app_on(backend_name, tmp_path)) as client:
        created = client.post("/api/topics", json={"request": "SQL", "profile": profile})
        topic = settle(client, created.json()["id"])

    assert topic["last_run"] == {"job": "next_lesson", "state": "done", "error": None}
    assert topic["syllabus"]["rationale"]
    first, second = topic["lessons"]
    # The two lessons fill the first two stops along the path, in order.
    stops = [u["unit_id"] for u in topic["path"] for _ in range(u["stops"])]
    placed = {i: u["unit_id"] for u in topic["path"] for i in u["lesson_ids"]}
    assert [placed[first["lesson_id"]], placed[second["lesson_id"]]] == stops[:2]


async def finished_topic(db: Database) -> str:
    """A topic whose every lesson has been taken."""
    profile = Profile(why="curiosity", depth="overview", level="new")
    topic = await TopicRepo(db).create(LOCAL_LEARNER, "Fractions", profile)
    units = [
        Unit(
            id=uid,
            title=title,
            summary=title,
            objectives=[Objective(id=f"obj_{uid}", text=title)],
            prerequisites=prerequisites,
        )
        for uid, title, prerequisites in [
            ("what", "What a fraction is", []),
            ("adding", "Adding fractions", ["what"]),
        ]
    ]
    syllabus = Syllabus(
        id="syl_1",
        topic="Fractions",
        goal="Understand and add fractions",
        rationale="A quick overview, from the beginning.",
        units=units,
    )
    await SyllabusRepo(db).create(LOCAL_LEARNER, syllabus, topic.id)
    for unit in units:
        question = TrueFalse(
            id="q1",
            prompt=f"True or false: {unit.title.lower()} is easy.",
            difficulty=1,
            explanation="It is, with practice.",
            answer=True,
            objective_ids=[f"obj_{unit.id}"],
        )
        lesson = Lesson(
            id=f"les_{unit.id}",
            title=unit.title,
            purpose="lesson",
            syllabus_id="syl_1",
            unit_id=unit.id,
            items=[question],
        )
        await LessonRepo(db).create(LOCAL_LEARNER, lesson, topic.id)
        answer = Answer(response=BoolResponse(value=True), correct=True)
        attempt = Attempt(
            id=f"att_{unit.id}",
            lesson_id=lesson.id,
            answers={"q1": answer},
            submitted_at=datetime.now(UTC),
        )
        await AttemptRepo(db).submit(LOCAL_LEARNER, attempt)
    return topic.id


def test_a_finished_topic_goes_further(backend_name, tmp_path):
    app = app_on(backend_name, tmp_path)
    with TestClient(app) as client:
        topic_id = client.portal.call(finished_topic, app.state.db)
        assert client.get(f"/api/topics/{topic_id}").json()["finished"]
        assert client.post(f"/api/topics/{topic_id}/extend").status_code == 202
        topic = settle(client, topic_id)

    assert topic["last_run"]["state"] == "done", topic["last_run"]
    assert not topic["finished"]
    units = [u["unit_id"] for u in topic["path"]]
    assert units[:2] == ["what", "adding"]  # kept as they were
    first_new = topic["path"][2]
    assert first_new["lesson_ids"]  # its lessons followed the extend run
