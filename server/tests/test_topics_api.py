import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pupil_server.agents import AgentConfig
from pupil_server.agents.fake import Call, FakeBackend, FakeSession, Say
from pupil_server.app import create_app
from pupil_server.db import LOCAL_LEARNER
from pupil_server.db.runs import RunRepo
from pupil_server.runs.log import UserMessage
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


def unit(uid: str, lessons: int) -> dict:
    title = uid.title()
    return {
        "id": uid,
        "title": title,
        "summary": "",
        "objectives": [{"text": title}],
        "lessons": lessons,
    }


def plan(basics: int = 2, joins: int = 1) -> dict:
    return {
        "topic": "SQL",
        "goal": "Query my team's data",
        "rationale": "Practical first, starting from joins since you know the basics.",
        "units": [unit("basics", basics), unit("joins", joins)],
    }


class Scripted:
    """Calls for the fake agent to make on the syllabus it created, whose ids the app
    assigned."""

    def __init__(self) -> None:
        self.syllabus: dict[str, Any] | None = None

    def _remember(self, outputs: list[Any]) -> dict[str, Any]:
        # The syllabus as last created or revised, in this run or an earlier one.
        for output in outputs:
            if isinstance(output, dict) and "syllabus" in output:
                self.syllabus = output["syllabus"]
        assert self.syllabus is not None
        return self.syllabus

    def lesson(self, title: str, unit_id: str) -> Call:
        def arguments(outputs: list[Any]) -> dict[str, Any]:
            syllabus = self._remember(outputs)
            unit = next(u for u in syllabus["units"] if u["id"] == unit_id)
            question = {**QUESTION, "objective_ids": [unit["objectives"][0]["id"]]}
            return {
                "title": title,
                "purpose": "lesson",
                "syllabus_id": syllabus["id"],
                "unit_id": unit_id,
                "items": [question],
            }

        return Call("create_lesson", arguments)

    def add_unit(self, unit_id: str, lessons: int) -> Call:
        def arguments(outputs: list[Any]) -> dict[str, Any]:
            syllabus = self._remember(outputs)
            return {
                "syllabus_id": syllabus["id"],
                "based_on_revision": syllabus["revision"],
                "topic": syllabus["topic"],
                "goal": syllabus["goal"],
                "rationale": "Now window functions too.",
                "units": [*syllabus["units"], unit(unit_id, lessons)],
            }

        return Call("revise_syllabus", arguments)

    def reread(self) -> Call:
        """Read the syllabus again, so a later run's lessons see this run's revision."""

        def arguments(outputs: list[Any]) -> dict[str, Any]:
            return {"syllabus_id": self._remember(outputs)["id"]}

        return Call("get_syllabus", arguments)


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


def titles(topic: dict) -> list[str]:
    return [x["title"] for x in topic["lessons"]]


def test_a_topic_goes_from_placement_to_a_plan_to_lessons_written_ahead(app_with):
    script = Scripted()
    backend = FakeBackend(
        [
            [Call("create_lesson", PLACEMENT)],
            [Call("create_syllabus", plan()), script.lesson("Basics 1", "basics")],
            [script.lesson("Basics 2", "basics")],  # straight after, while Basics 1 is taken
            [script.lesson("Joins", "joins")],
        ]
    )
    with TestClient(app_with(backend)) as c:
        topic = settle(c, start(c)["id"])
        assert titles(topic) == ["Placement"]
        assert topic["next_lesson_id"] == topic["lessons"][0]["lesson_id"]
        assert topic["last_run"] == {"job": "placement", "state": "done", "error": None}

        take(c, topic["next_lesson_id"])
        topic = settle(c, topic["id"])
        assert topic["syllabus"]["rationale"] == plan()["rationale"]
        assert titles(topic) == ["Placement", "Basics 1", "Basics 2"]  # one lesson ahead
        assert topic["next_lesson_id"] == topic["lessons"][1]["lesson_id"]
        assert topic["last_run"] == {"job": "next_lesson", "state": "done", "error": None}

        take(c, topic["next_lesson_id"])
        topic = settle(c, topic["id"])
        assert titles(topic) == ["Placement", "Basics 1", "Basics 2", "Joins"]

    briefs = [s.received[0] for s in backend.sessions]
    assert "'Placement' (" in briefs[1].split("# Results since your last run\n")[1]
    assert "lesson 2 of 2 (the unit's last) in unit 'basics'" in briefs[2]
    results_since = briefs[3].split("# Results since your last run\n")[1]
    assert results_since.startswith("'Basics 1'")  # only what happened since the last run


def test_the_path_has_every_stop_and_ends_when_all_are_taken(app_with):
    script = Scripted()
    backend = FakeBackend(
        [
            [Call("create_syllabus", plan(basics=1, joins=1)), script.lesson("Basics", "basics")],
            [script.lesson("Joins", "joins")],
        ]
    )
    with TestClient(app_with(backend)) as c:
        topic = settle(c, start(c, level="new")["id"])  # nothing to place
        basics, joins = (x["lesson_id"] for x in topic["lessons"])
        assert [(u["unit_id"], u["stops"], u["lesson_ids"]) for u in topic["path"]] == [
            ("basics", 1, [basics]),
            ("joins", 1, [joins]),
        ]

        take(c, basics)
        topic = settle(c, topic["id"])
        assert not topic["finished"]
        take(c, joins)
        topic = settle(c, topic["id"])
    assert topic["finished"]
    assert topic["next_lesson_id"] is None
    assert len(backend.sessions) == 2  # nothing more is written once the path is


def test_a_finished_topic_can_go_further(app_with):
    script = Scripted()
    backend = FakeBackend(
        [
            [Call("create_syllabus", plan(basics=1, joins=1)), script.lesson("Basics", "basics")],
            [script.lesson("Joins", "joins")],
            [script.add_unit("windows", 1), script.reread()],
            [script.lesson("Windows", "windows")],
        ]
    )
    with TestClient(app_with(backend)) as c:
        topic_id = start(c, level="new")["id"]
        assert c.post(f"/api/topics/{topic_id}/extend").status_code == 409  # not finished
        for lesson in settle(c, topic_id)["lessons"]:
            take(c, lesson["lesson_id"])
        assert settle(c, topic_id)["finished"]

        assert c.post(f"/api/topics/{topic_id}/extend").status_code == 202
        topic = settle(c, topic_id)
    assert not topic["finished"]
    assert [u["unit_id"] for u in topic["path"]] == ["basics", "joins", "windows"]
    assert titles(topic) == ["Basics", "Joins", "Windows"]


def test_a_run_that_makes_nothing_fails_and_can_be_tried_again(app_with):
    backend = FakeBackend([[Say("I'd rather not")], [Call("create_lesson", PLACEMENT)]])
    with TestClient(app_with(backend)) as c:
        topic = settle(c, start(c)["id"])
        assert topic["last_run"] == {
            "job": "placement",
            "state": "failed",
            "error": "the run didn't write a lesson",
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


def test_runs_use_the_model_and_effort_from_the_settings(tmp_path: Path):
    backend = FakeBackend([[Call("create_lesson", PLACEMENT)]])
    settings = Settings(model="m", effort="high")
    app = create_app(settings, db_path=tmp_path / "t.db", agent_backend=backend)
    with TestClient(app) as c:
        settle(c, start(c)["id"])
    config = backend.sessions[0].config
    assert (config.model, config.effort) == ("m", "high")


class Gated(FakeBackend):
    """A backend whose runs wait until the gate opens."""

    def __init__(self) -> None:
        super().__init__([[Call("create_lesson", PLACEMENT)]])
        self.gate = asyncio.Event()

    async def open_session(self, config: AgentConfig) -> FakeSession:
        session = await super().open_session(config)
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
