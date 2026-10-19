import asyncio
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pupil_server.agents import AgentConfig, TextDelta, TurnComplete
from pupil_server.agents.fake import Call, FakeBackend, FakeSession, Say
from pupil_server.agents.sessions import SessionBusy, SessionStore
from pupil_server.app import create_app
from pupil_server.db import LOCAL_LEARNER
from pupil_server.db.learning import SyllabusRepo
from pupil_server.settings import Settings


def _events(body: str) -> list[dict]:
    return [
        json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")
    ]


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend([[Say("Let me check"), Call("get_current_time")]])


@pytest.fixture
def client(tmp_path: Path, backend: FakeBackend):
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=backend)
    with TestClient(app) as c:
        yield c


def start(client: TestClient) -> str:
    created = client.post("/api/conversations")
    assert created.status_code == 201
    return created.json()["conversation_id"]


def say(client: TestClient, conversation_id: str, text: str) -> list[dict]:
    res = client.post(f"/api/conversations/{conversation_id}/messages", json={"text": text})
    assert res.status_code == 200
    return _events(res.text)


def transcript(client: TestClient, conversation_id: str) -> list[dict]:
    return client.get(f"/api/conversations/{conversation_id}").json()["transcript"]


# Streaming


def test_turn_is_sent_as_sse_events(client: TestClient):
    conversation_id = start(client)
    res = client.post(f"/api/conversations/{conversation_id}/messages", json={"text": "time?"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = _events(res.text)
    types = [e["type"] for e in events]
    assert types[0] == "text_delta" and types[-1] == "turn_complete"
    assert types.index("tool_call") < types.index("tool_result")
    call = next(e for e in events if e["type"] == "tool_call")
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["id"] == call["id"] and not result["is_error"]


def test_events_arrive_before_the_turn_ends(client: TestClient, backend: FakeBackend):
    conversation_id = start(client)
    say(client, conversation_id, "hello")  # opens the session
    gate = threading.Event()
    finished = threading.Event()

    async def paused_turn(text: str):
        yield TextDelta(text="first")
        # Bounded, so a buffering endpoint fails the assertion below instead of hanging.
        await asyncio.to_thread(gate.wait, 5)
        finished.set()
        yield TurnComplete()

    backend.sessions[0].send = paused_turn
    url = f"/api/conversations/{conversation_id}/messages"
    with client.stream("POST", url, json={"text": "x"}) as res:
        lines = (line for line in res.iter_lines() if line.startswith("data: "))
        first = json.loads(next(lines)[len("data: ") :])
        assert first == {"type": "text_delta", "text": "first"}
        assert not finished.is_set(), "first event was held back until the turn ended"

        gate.set()
        last = json.loads(list(lines)[-1][len("data: ") :])
    assert last["type"] == "turn_complete"


async def test_busy_session_is_rejected(backend: FakeBackend):
    store = SessionStore(backend)
    await store.open("conv_1", AgentConfig(system_prompt="Tutor"))
    stream = store.send(store.claim("conv_1"), "first")
    await anext(stream)  # turn in progress, lock held
    with pytest.raises(SessionBusy):
        store.claim("conv_1")
    await stream.aclose()


def test_backend_failure_becomes_error_event(client: TestClient, backend: FakeBackend):
    conversation_id = start(client)
    say(client, conversation_id, "hello")

    async def broken(text: str):
        raise ConnectionError("model went away")
        yield  # pragma: no cover

    backend.sessions[0].send = broken
    events = say(client, conversation_id, "x")
    assert events == [{"type": "error", "message": "ConnectionError: model went away"}]


# Transcripts


def test_transcript_saves_the_turn_with_text_merged(client: TestClient):
    conversation_id = start(client)
    say(client, conversation_id, "time?")

    items = transcript(client, conversation_id)
    assert [i["type"] for i in items] == [
        "user_message",
        "text_delta",
        "tool_call",
        "tool_result",
        "turn_complete",
    ]
    assert items[0]["text"] == "time?"
    assert items[1]["text"] == "Let me check "  # the fake streams it a word at a time


def test_conversations_are_listed_newest_first(client: TestClient):
    first, second = start(client), start(client)
    listed = client.get("/api/conversations").json()
    assert [c["conversation_id"] for c in listed] == [second, first]


def test_unknown_conversation_is_404(client: TestClient):
    assert client.get("/api/conversations/nope").status_code == 404
    res = client.post("/api/conversations/nope/messages", json={"text": "hi"})
    assert res.status_code == 404
    assert client.delete("/api/conversations/nope/session").status_code == 404


# Live sessions


def test_the_session_opens_with_the_first_message(client: TestClient, backend: FakeBackend):
    conversation_id = start(client)
    assert backend.sessions == []
    say(client, conversation_id, "hello")
    assert len(backend.sessions) == 1


def test_a_released_session_is_resumed_by_the_next_message(
    client: TestClient, backend: FakeBackend
):
    conversation_id = start(client)
    say(client, conversation_id, "hello")
    first = backend.sessions[0]

    assert client.delete(f"/api/conversations/{conversation_id}/session").status_code == 204
    assert first.closed

    say(client, conversation_id, "again")
    assert backend.resumed == [first.resume_token]


def test_a_conversation_carries_on_after_a_restart(tmp_path: Path):
    path = tmp_path / "t.db"
    before = FakeBackend()
    with TestClient(create_app(Settings(), db_path=path, agent_backend=before)) as c:
        conversation_id = start(c)
        say(c, conversation_id, "hello")

    after = FakeBackend()
    with TestClient(create_app(Settings(), db_path=path, agent_backend=after)) as c:
        say(c, conversation_id, "still there?")
        items = transcript(c, conversation_id)

    assert after.resumed == [before.sessions[0].resume_token]
    said = [i["text"] for i in items if i["type"] == "user_message"]
    assert said == ["hello", "still there?"]


def test_a_session_that_cannot_be_resumed_starts_afresh(client: TestClient, backend: FakeBackend):
    conversation_id = start(client)
    say(client, conversation_id, "hello")
    client.delete(f"/api/conversations/{conversation_id}/session")

    async def lost(config: AgentConfig, resume: str | None = None) -> FakeSession:
        if resume:
            raise FileNotFoundError("no such session")
        return await FakeBackend.open_session(backend, config)

    backend.open_session = lost
    events = say(client, conversation_id, "again")
    assert events[-1]["type"] == "turn_complete"
    assert len(backend.sessions) == 2


def test_sessions_closed_on_shutdown(tmp_path: Path, backend: FakeBackend):
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=backend)
    with TestClient(app) as c:
        say(c, start(c), "hello")
    assert backend.sessions[0].closed


# Tools


def test_tutor_tools_write_to_the_apps_database(tmp_path: Path):
    plan = {
        "topic": "Python",
        "goal": "Write small scripts",
        "units": [
            {"id": "basics", "title": "Basics", "summary": "", "objectives": [{"text": "t"}]}
        ],
    }
    backend = FakeBackend([[Call("create_syllabus", plan)]])
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=backend)
    with TestClient(app) as c:
        events = say(c, start(c), "plan it")
        result = next(e for e in events if e["type"] == "tool_result")
        assert not result["is_error"]

        stored = c.portal.call(SyllabusRepo(app.state.db).list_latest, LOCAL_LEARNER)
    assert [s.topic for s in stored] == ["Python"]


QUIZ_PLAN = {
    "title": "Placement",
    "purpose": "placement",
    "questions": [
        {"kind": "true_false", "id": "q1", "prompt": "p", "difficulty": 1, "answer": True}
    ],
}


def test_the_quiz_answer_key_stays_out_of_the_stream_and_transcript(tmp_path: Path):
    backend = FakeBackend([[Call("create_quiz", QUIZ_PLAN)]])
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=backend)
    with TestClient(app) as c:
        conversation_id = start(c)
        events = say(c, conversation_id, "quiz me")
        items = transcript(c, conversation_id)

    streamed = next(e for e in events if e["type"] == "tool_call")
    saved = next(i for i in items if i["type"] == "tool_call")
    assert streamed["input"] == {}
    assert saved["input"] == {}
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["output"]["quiz_id"].startswith("quiz_")  # how the client finds the quiz


def test_quiz_results_are_reported_to_the_agent(tmp_path: Path):
    backend = FakeBackend([[Call("create_quiz", QUIZ_PLAN)], [Say("Well done")]])
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=backend)
    with TestClient(app) as c:
        conversation_id = start(c)
        events = say(c, conversation_id, "quiz me")
        quiz_id = next(e for e in events if e["type"] == "tool_result")["output"]["quiz_id"]
        attempt = c.post(
            f"/api/quizzes/{quiz_id}/attempts",
            json={"responses": {"q1": {"kind": "bool", "value": True}}},
        ).json()

        url = f"/api/conversations/{conversation_id}/quiz-results"
        res = c.post(url, json={"attempt_id": attempt["attempt_id"]})
        assert _events(res.text)[-1]["type"] == "turn_complete"
        items = transcript(c, conversation_id)
        missing = c.post(url, json={"attempt_id": "att_nope"})

    told = backend.sessions[0].received[-1]
    assert (
        told
        == "The learner finished the quiz 'Placement' (" + quiz_id + "): 1 of 1 right.\n- q1: right"
    )
    reported = next(i for i in items if i["type"] == "quiz_results")
    assert reported["attempt_id"] == attempt["attempt_id"]
    assert (reported["correct"], reported["total"]) == (1, 1)
    assert reported["text"] == told
    assert missing.status_code == 404
