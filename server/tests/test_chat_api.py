import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pupil_server.agents.fake import Call, FakeBackend, Say
from pupil_server.app import create_app
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


def test_chat_round_trip_streams_events(client: TestClient):
    created = client.post("/api/chat/sessions")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    res = client.post(f"/api/chat/sessions/{session_id}/messages", json={"text": "time?"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = _events(res.text)
    types = [e["type"] for e in events]
    assert types[-1] == "turn_complete"
    result = next(e for e in events if e["type"] == "tool_result")
    assert not result["is_error"] and "T" in result["output"]  # an ISO timestamp


def test_unknown_session_is_404(client: TestClient):
    assert client.post("/api/chat/sessions/nope/messages", json={"text": "hi"}).status_code == 404
    assert client.delete("/api/chat/sessions/nope").status_code == 404


def test_delete_closes_the_session(client: TestClient, backend: FakeBackend):
    session_id = client.post("/api/chat/sessions").json()["session_id"]
    assert client.delete(f"/api/chat/sessions/{session_id}").status_code == 204
    assert backend.sessions[0].closed


async def test_busy_session_is_rejected(tmp_path: Path, backend: FakeBackend):
    from pupil_server.agents.demo import demo_config
    from pupil_server.agents.sessions import SessionBusy, SessionStore

    store = SessionStore(backend)
    session_id = await store.open(demo_config())
    stream = store.send(store.claim(session_id), "first")
    await anext(stream)  # turn in progress, lock held
    with pytest.raises(SessionBusy):
        store.claim(session_id)
    await stream.aclose()


def test_backend_failure_becomes_error_event(client: TestClient, backend: FakeBackend):
    session_id = client.post("/api/chat/sessions").json()["session_id"]

    async def broken(text: str):
        raise ConnectionError("model went away")
        yield  # pragma: no cover

    backend.sessions[0].send = broken
    events = _events(
        client.post(f"/api/chat/sessions/{session_id}/messages", json={"text": "x"}).text
    )
    assert events == [{"type": "error", "message": "ConnectionError: model went away"}]


def test_sessions_closed_on_shutdown(tmp_path: Path, backend: FakeBackend):
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=backend)
    with TestClient(app) as c:
        c.post("/api/chat/sessions")
    assert backend.sessions[0].closed
