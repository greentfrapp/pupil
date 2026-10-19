from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pupil_server.agents.fake import FakeBackend
from pupil_server.app import create_app
from pupil_server.db import LOCAL_LEARNER
from pupil_server.db.learning import QuizRepo
from pupil_server.learning.quiz import Numeric, Quiz, TrueFalse
from pupil_server.settings import Settings

QUIZ = Quiz(
    id="quiz_1",
    title="Placement",
    purpose="placement",
    questions=[
        TrueFalse(id="q1", prompt="Lists are mutable", difficulty=1, answer=True),
        Numeric(id="q2", prompt="len('abc')?", difficulty=1, answer=3, explanation="Three letters"),
    ],
)


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(Settings(), db_path=tmp_path / "t.db", agent_backend=FakeBackend())
    with TestClient(app) as c:
        c.portal.call(QuizRepo(app.state.db).create, LOCAL_LEARNER, QUIZ)
        yield c


def submit(client: TestClient, responses: dict):
    return client.post("/api/quizzes/quiz_1/attempts", json={"responses": responses})


def test_the_quiz_is_served_without_answers(client: TestClient):
    res = client.get("/api/quizzes/quiz_1")
    assert res.status_code == 200
    body = res.json()
    assert [q["id"] for q in body["quiz"]["questions"]] == ["q1", "q2"]
    assert "answer" not in res.text
    assert "Three letters" not in res.text
    assert body["attempt"] is None


def test_answers_are_graded_and_explained(client: TestClient):
    res = submit(client, {"q2": {"kind": "number", "value": 3}})
    assert res.status_code == 201
    attempt = res.json()
    assert attempt["attempt_id"].startswith("att_")
    assert attempt["correct"] == 1
    assert attempt["total"] == 2
    assert attempt["results"] == [
        {"question_id": "q1", "correct": False, "response": None, "explanation": None},
        {
            "question_id": "q2",
            "correct": True,
            "response": {"kind": "number", "value": 3.0},
            "explanation": "Three letters",
        },
    ]


def test_a_quiz_is_answered_once_and_then_shows_its_results(client: TestClient):
    first = submit(client, {"q1": {"kind": "bool", "value": True}}).json()
    assert submit(client, {"q1": {"kind": "bool", "value": False}}).status_code == 409
    assert client.get("/api/quizzes/quiz_1").json()["attempt"] == first


def test_answers_that_dont_fit_the_quiz_are_refused(client: TestClient):
    wrong_kind = submit(client, {"q1": {"kind": "text", "text": "yes"}})
    assert wrong_kind.status_code == 422
    assert "needs a BoolResponse" in wrong_kind.json()["detail"]
    unknown = submit(client, {"q9": {"kind": "bool", "value": True}})
    assert unknown.status_code == 422
    assert client.get("/api/quizzes/quiz_1").json()["attempt"] is None


def test_unknown_quiz_is_404(client: TestClient):
    assert client.get("/api/quizzes/nope").status_code == 404
    assert client.post("/api/quizzes/nope/attempts", json={"responses": {}}).status_code == 404
