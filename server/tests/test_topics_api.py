import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pupil_server.agents import AgentConfig
from pupil_server.agents.fake import Call, FakeBackend, FakeSession, Say
from pupil_server.app import create_app
from pupil_server.conversations.transcript import UserMessage
from pupil_server.db import LOCAL_LEARNER
from pupil_server.db.runs import RunRepo
from pupil_server.settings import Settings

QUESTION = {
    "kind": "true_false",
    "id": "q1",
    "prompt": "p",
    "difficulty": 1,
    "explanation": "e",
    "answer": True,
}
PLACEMENT = {"title": "Placement", "purpose": "placement", "items": [QUESTION]}
PLAN = {
    "topic": "SQL",
    "goal": "Query my team's data",
    "units": [{"id": "basics", "title": "Basics", "summary": "", "objectives": [{"text": "t"}]}],
}


class Scripted:
    """Lessons for the fake agent to write, tied to the syllabus it created, whose ids the app
    assigned."""

    def __init__(self) -> None:
        self.syllabus: dict[str, Any] | None = None

    def lesson(self, title: str) -> Call:
        def arguments(outputs: list[Any]) -> dict[str, Any]:
            # Remember the syllabus when it was created earlier in the same run.
            for output in outputs:
                if isinstance(output, dict) and "syllabus" in output:
                    self.syllabus = output["syllabus"]
            assert self.syllabus is not None
            objective = self.syllabus["units"][0]["objectives"][0]["id"]
            question = {**QUESTION, "objective_ids": [objective]}
            return {
                "title": title,
                "purpose": "lesson",
                "syllabus_id": self.syllabus["id"],
                "items": [question],
            }

        return Call("create_lesson", arguments)


def start(client: TestClient, level: str = "basics") -> dict:
    profile = {"why": "work", "depth": "working", "level": level}
    created = client.post("/api/topics", json={"request": "SQL", "profile": profile})
    assert created.status_code == 201
    return created.json()


def settle(client: TestClient, topic_id: str) -> dict:
    """The topic, once its run (if any) has ended."""
    client.portal.call(client.app.state.runs.wait, topic_id)
    return client.get(f"/api/topics/{topic_id}").json()


def take(client: TestClient, lesson_id: str) -> None:
    answers = {"q1": {"response": {"kind": "bool", "value": True}, "correct": True}}
    res = client.post(f"/api/lessons/{lesson_id}/attempts", json={"answers": answers})
    assert res.status_code == 201


@pytest.fixture
def app_with(tmp_path: Path):
    def make(backend: FakeBackend):
        return create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=backend)

    return make


def test_a_topic_goes_from_placement_to_a_plan_to_lessons(app_with):
    script = Scripted()
    backend = FakeBackend(
        [
            [Call("create_lesson", PLACEMENT)],
            [
                Call("create_syllabus", PLAN),
                Call("add_note", {"text": "starts from scratch"}),
                script.lesson("First"),
            ],
            [script.lesson("Second")],
        ]
    )
    with TestClient(app_with(backend)) as c:
        topic = settle(c, start(c)["id"])
        assert [x["purpose"] for x in topic["lessons"]] == ["placement"]
        assert topic["next_lesson_id"] == topic["lessons"][0]["lesson_id"]
        assert topic["last_run"] == {"job": "placement", "state": "done", "error": None}

        take(c, topic["next_lesson_id"])
        topic = settle(c, topic["id"])
        assert topic["syllabus"]["goal"] == "Query my team's data"
        assert [x["title"] for x in topic["lessons"]] == ["Placement", "First"]
        assert topic["next_lesson_id"] == topic["lessons"][1]["lesson_id"]
        assert topic["last_run"]["job"] == "plan"

        take(c, topic["next_lesson_id"])
        topic = settle(c, topic["id"])
        assert [x["title"] for x in topic["lessons"]] == ["Placement", "First", "Second"]
        assert topic["last_run"] == {"job": "next_lesson", "state": "done", "error": None}

    briefs = [s.received[0] for s in backend.sessions]
    assert "'First'" not in briefs[1] and "'Placement' (" in briefs[1]  # placement results
    assert "# Your notes\n- starts from scratch" in briefs[2]
    results_since = briefs[2].split("# Results since your last run\n")[1]
    assert results_since.startswith("'First'")  # only what happened since the plan run


def test_a_learner_new_to_the_topic_skips_placement(app_with):
    script = Scripted()
    backend = FakeBackend([[Call("create_syllabus", PLAN), script.lesson("First")]])
    with TestClient(app_with(backend)) as c:
        topic = settle(c, start(c, level="new")["id"])
    assert topic["last_run"]["job"] == "plan"
    assert [x["title"] for x in topic["lessons"]] == ["First"]


def test_a_run_that_makes_nothing_fails_and_can_be_tried_again(app_with):
    backend = FakeBackend([[Say("I'd rather not")], [Call("create_lesson", PLACEMENT)]])
    with TestClient(app_with(backend)) as c:
        topic = settle(c, start(c)["id"])
        assert topic["last_run"] == {
            "job": "placement",
            "state": "failed",
            "error": "the run didn't leave a lesson to take",
        }
        assert topic["next_lesson_id"] is None

        assert c.post(f"/api/topics/{topic['id']}/prepare").status_code == 202
        topic = settle(c, topic["id"])
    assert topic["last_run"]["state"] == "done"
    assert topic["next_lesson_id"] is not None


def test_a_run_is_logged_from_its_brief(app_with):
    backend = FakeBackend([[Call("create_lesson", PLACEMENT)]])
    app = app_with(backend)
    with TestClient(app) as c:
        topic_id = settle(c, start(c)["id"])["id"]
        runs = RunRepo(app.state.db)
        run = c.portal.call(runs.latest, LOCAL_LEARNER, topic_id)
        log = c.portal.call(runs.log, LOCAL_LEARNER, run.id)
    assert log[0] == UserMessage(text=backend.sessions[0].received[0])
    assert [item.type for item in log[1:]] == ["tool_call", "tool_result", "turn_complete"]
    assert run.cost_usd == 0.0


class Gated(FakeBackend):
    """A backend whose runs wait until the gate opens."""

    def __init__(self) -> None:
        super().__init__([[Call("create_lesson", PLACEMENT)]])
        self.gate = asyncio.Event()

    async def open_session(self, config: AgentConfig, resume: str | None = None) -> FakeSession:
        session = await super().open_session(config, resume)
        send = session.send

        async def gated(text: str):
            await self.gate.wait()
            async for event in send(text):
                yield event

        session.send = gated
        return session


def test_only_one_run_goes_per_topic(app_with):
    backend = Gated()
    with TestClient(app_with(backend)) as c:
        topic_id = start(c)["id"]
        again = c.post(f"/api/topics/{topic_id}/prepare").json()
        assert again["last_run"] == {"job": "placement", "state": "running", "error": None}

        c.portal.call(backend.gate.set)
        topic = settle(c, topic_id)
    assert topic["last_run"]["state"] == "done"
    assert len(backend.sessions) == 1  # the second prepare started nothing


def test_a_run_cut_off_by_shutdown_is_recorded(app_with):
    with TestClient(app_with(Gated())) as c:
        topic_id = start(c)["id"]  # its run waits at the gate until shutdown
    with TestClient(app_with(FakeBackend())) as c:
        topic = c.get(f"/api/topics/{topic_id}").json()
    assert topic["last_run"] == {
        "job": "placement",
        "state": "failed",
        "error": "the run was cut off",
    }


def test_topics_are_listed_newest_first_and_unknown_ones_are_404(app_with):
    with TestClient(app_with(FakeBackend())) as c:
        first, second = start(c)["id"], start(c)["id"]
        assert [t["id"] for t in c.get("/api/topics").json()] == [second, first]
        assert c.get("/api/topics/nope").status_code == 404
        assert c.post("/api/topics/nope/prepare").status_code == 404
