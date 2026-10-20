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


def check(client: TestClient, question_id: str, response: dict, lesson_id: str = "les_1"):
    body = {"question_id": question_id, "response": response}
    return client.post(f"/api/lessons/{lesson_id}/check", json=body)


def submit(client: TestClient, responses: dict, lesson_id: str = "les_1"):
    return client.post(f"/api/lessons/{lesson_id}/attempts", json={"responses": responses})


# Getting a lesson


def test_the_lesson_is_served_without_answers(client: TestClient):
    res = client.get("/api/lessons/les_1")
    assert res.status_code == 200
    body = res.json()
    assert sorted(i["id"] for i in body["lesson"]["items"]) == ["c1", "q1", "q2"]
    assert body["lesson"]["items"][0] == {
        "kind": "teach_card",
        "id": "c1",
        "title": "Lists",
        "text": "A list holds items.",
    }
    assert "answer" not in res.text
    assert "Three letters" not in res.text
    assert body["attempts"] == []


def test_the_lesson_lists_its_attempts(client: TestClient):
    submit(client, {"q1": {"kind": "bool", "value": True}})
    submit(client, {})
    attempts = client.get("/api/lessons/les_1").json()["attempts"]
    assert [(a["number"], a["correct"], a["total"]) for a in attempts] == [(1, 1, 2), (2, 0, 2)]


# Checking each answer


def test_an_answer_is_checked_with_the_correct_answer_and_explanation(client: TestClient):
    wrong = check(client, "q2", {"kind": "number", "value": 4})
    assert wrong.status_code == 200
    assert wrong.json() == {"correct": False, "answer": "3", "explanation": "Three letters"}
    right = check(client, "q2", {"kind": "number", "value": 3})
    assert right.json()["correct"] is True


def test_checking_stores_nothing(client: TestClient):
    check(client, "q1", {"kind": "bool", "value": True})
    assert client.get("/api/lessons/les_1").json()["attempts"] == []


def test_checks_that_dont_fit_the_lesson_are_refused(client: TestClient):
    wrong_kind = check(client, "q1", {"kind": "text", "text": "yes"})
    assert wrong_kind.status_code == 422
    assert "needs a BoolResponse" in wrong_kind.json()["detail"]
    teach_card = check(client, "c1", {"kind": "bool", "value": True})
    assert teach_card.status_code == 422
    assert "no question 'c1'" in teach_card.json()["detail"]


# Submitting an attempt


def test_an_attempt_is_graded_with_answers_and_explanations(client: TestClient):
    res = submit(client, {"q2": {"kind": "number", "value": 3}})
    assert res.status_code == 201
    attempt = res.json()
    assert attempt["attempt_id"].startswith("att_")
    assert (attempt["number"], attempt["correct"], attempt["total"]) == (1, 1, 2)
    assert attempt["results"] == [
        {
            "question_id": "q1",
            "correct": False,
            "response": None,
            "answer": "True",
            "explanation": "You can change a list in place.",
        },
        {
            "question_id": "q2",
            "correct": True,
            "response": {"kind": "number", "value": 3.0},
            "answer": "3",
            "explanation": "Three letters",
        },
    ]


def test_a_lesson_can_be_retried(client: TestClient):
    first = submit(client, {})
    retry = submit(client, {"q1": {"kind": "bool", "value": True}})
    assert (first.status_code, retry.status_code) == (201, 201)
    assert retry.json()["number"] == 2


def test_placement_cant_be_retried(client: TestClient):
    assert submit(client, {}, "les_p").status_code == 201
    again = submit(client, {}, "les_p")
    assert again.status_code == 409
    assert len(client.get("/api/lessons/les_p").json()["attempts"]) == 1


def test_attempts_that_dont_fit_the_lesson_are_refused(client: TestClient):
    wrong_kind = submit(client, {"q1": {"kind": "text", "text": "yes"}})
    assert wrong_kind.status_code == 422
    assert "needs a BoolResponse" in wrong_kind.json()["detail"]
    unknown = submit(client, {"q9": {"kind": "bool", "value": True}})
    assert unknown.status_code == 422
    assert client.get("/api/lessons/les_1").json()["attempts"] == []


def test_unknown_lesson_is_404(client: TestClient):
    assert client.get("/api/lessons/nope").status_code == 404
    assert check(client, "q1", {"kind": "bool", "value": True}, "nope").status_code == 404
    assert submit(client, {}, "nope").status_code == 404
