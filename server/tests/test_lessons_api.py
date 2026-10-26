from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pupil_server.agents.fake import FakeBackend
from pupil_server.app import create_app
from pupil_server.db import LOCAL_LEARNER
from pupil_server.db.learning import LessonRepo, SyllabusRepo
from pupil_server.learning.lesson import Lesson, Numeric, TeachCard, TrueFalse
from pupil_server.learning.syllabus import Syllabus
from pupil_server.settings import Settings

SYLLABUS = Syllabus(
    id="syl_1",
    topic="Python",
    goal="g",
    units=[{"id": "u1", "title": "U", "summary": "", "objectives": [{"id": "o1", "text": "t"}]}],
)


def questions(tags: list[str]) -> list:
    return [
        TrueFalse(
            id="q1",
            prompt="Lists are mutable",
            difficulty=1,
            explanation="You can change a list in place.",
            answer=True,
            objective_ids=tags,
        ),
        Numeric(
            id="q2",
            prompt="len('abc')?",
            difficulty=1,
            explanation="Three letters",
            answer=3,
            objective_ids=tags,
        ),
    ]


LESSON = Lesson(
    id="les_1",
    title="Lists",
    purpose="lesson",
    syllabus_id="syl_1",
    unit_id="u1",
    items=[TeachCard(id="c1", title="Lists", text="A list holds items."), *questions(["o1"])],
)

PLACEMENT = Lesson(id="les_p", title="Placement", purpose="placement", items=questions([]))


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=FakeBackend())
    with TestClient(app) as c:
        c.portal.call(SyllabusRepo(app.state.db).create, LOCAL_LEARNER, SYLLABUS)
        for lesson in (LESSON, PLACEMENT):
            c.portal.call(LessonRepo(app.state.db).create, LOCAL_LEARNER, lesson)
        yield c


SKIPPED = {"response": None, "correct": False}
RIGHT_Q1 = {"response": {"kind": "bool", "value": True}, "correct": True}


def submit(client: TestClient, answers: dict, lesson_id: str = "les_1"):
    every = {"q1": SKIPPED, "q2": SKIPPED, **answers}
    return client.post(f"/api/lessons/{lesson_id}/attempts", json={"answers": every})


# Getting a lesson


def test_the_lesson_is_served_with_its_answers_for_the_player(client: TestClient):
    res = client.get("/api/lessons/les_1")
    assert res.status_code == 200
    body = res.json()
    items = {i["id"]: i for i in body["lesson"]["items"]}
    assert body["lesson"]["items"][0]["id"] == "c1"  # nothing moves past a teach card
    assert items["q2"]["answer"] == 3
    assert items["q2"]["explanation"] == "Three letters"
    assert body["attempts"] == []


def test_the_lesson_lists_its_attempts(client: TestClient):
    submit(client, {"q1": RIGHT_Q1})
    submit(client, {})
    attempts = client.get("/api/lessons/les_1").json()["attempts"]
    assert [(a["number"], a["correct"], a["total"]) for a in attempts] == [(1, 1, 2), (2, 0, 2)]


# Submitting an attempt


def test_an_attempt_is_stored_as_graded_by_the_player(client: TestClient):
    res = submit(client, {"q1": RIGHT_Q1})
    assert res.status_code == 201
    summary = res.json()
    assert summary["attempt_id"].startswith("att_")
    assert (summary["number"], summary["correct"], summary["total"]) == (1, 1, 2)


def test_a_lesson_can_be_retried(client: TestClient):
    first = submit(client, {})
    retry = submit(client, {"q1": RIGHT_Q1})
    assert (first.status_code, retry.status_code) == (201, 201)
    assert retry.json()["number"] == 2


def test_placement_cant_be_retried(client: TestClient):
    assert submit(client, {}, "les_p").status_code == 201
    again = submit(client, {}, "les_p")
    assert again.status_code == 409
    assert len(client.get("/api/lessons/les_p").json()["attempts"]) == 1


def test_attempts_that_dont_fit_the_lesson_are_refused(client: TestClient):
    wrong_kind = submit(
        client, {"q1": {"response": {"kind": "text", "text": "yes"}, "correct": True}}
    )
    assert wrong_kind.status_code == 422
    assert "needs a BoolResponse" in wrong_kind.json()["detail"]
    unknown = submit(client, {"q9": SKIPPED})
    assert unknown.status_code == 422
    missing = client.post("/api/lessons/les_1/attempts", json={"answers": {"q1": SKIPPED}})
    assert missing.status_code == 422
    assert "no answers to questions ['q2']" in missing.json()["detail"]
    assert client.get("/api/lessons/les_1").json()["attempts"] == []


def test_unknown_lesson_is_404(client: TestClient):
    assert client.get("/api/lessons/nope").status_code == 404
    assert submit(client, {}, "nope").status_code == 404
