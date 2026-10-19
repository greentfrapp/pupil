from pathlib import Path
from typing import Any

import pytest

from pupil_server.agents import ToolResult
from pupil_server.db import LOCAL_LEARNER, Database
from pupil_server.db.learning import EvidenceRepo, QuizRepo, SyllabusRepo
from pupil_server.learning.tools import learning_tools


@pytest.fixture
async def db(tmp_path: Path):
    db = await Database.open(tmp_path / "pupil.db")
    yield db
    await db.close()


@pytest.fixture
def call(db: Database):
    tools = {t.name: t for t in learning_tools(db, LOCAL_LEARNER)}

    async def call(name: str, **arguments: Any) -> ToolResult:
        return await tools[name].invoke("call_1", arguments)

    return call


def unit(uid: str, *prerequisites: str) -> dict:
    return {
        "id": uid,
        "title": uid.title(),
        "summary": "",
        "objectives": [{"id": f"{uid}_obj", "text": f"Can do {uid}"}],
        "prerequisites": list(prerequisites),
    }


PLAN = {"topic": "Python", "goal": "Write small scripts", "units": [unit("basics")]}

QUESTIONS = [
    {
        "kind": "multiple_choice",
        "id": "q1",
        "prompt": "Which keyword defines a function?",
        "difficulty": 1,
        "options": [{"id": "a", "text": "def"}, {"id": "b", "text": "fun"}],
        "correct": ["a"],
    },
    {"kind": "numeric", "id": "q2", "prompt": "len('abc')?", "difficulty": 1, "answer": 3},
]


def tagged(objective_id: str) -> list[dict]:
    return [{**q, "objective_ids": [objective_id]} for q in QUESTIONS]


async def test_create_syllabus_assigns_the_id(call, db: Database):
    result = await call("create_syllabus", **PLAN)
    assert not result.is_error
    assert result.output["syllabus_id"].startswith("syl_")
    assert result.output["revision"] == 1
    stored = await SyllabusRepo(db).get(LOCAL_LEARNER, result.output["syllabus_id"])
    assert stored.units[0].id == "basics"


async def test_an_invalid_syllabus_comes_back_as_an_error(call, db: Database):
    result = await call("create_syllabus", **{**PLAN, "units": [unit("a", "b"), unit("b", "a")]})
    assert result.is_error
    assert "prerequisite cycle: a -> b -> a" in result.output
    assert await SyllabusRepo(db).list_latest(LOCAL_LEARNER) == []


async def test_revise_syllabus_needs_the_revision_it_was_based_on(call):
    syllabus_id = (await call("create_syllabus", **PLAN)).output["syllabus_id"]
    change = {**PLAN, "units": [unit("basics"), unit("loops", "basics")]}

    revised = await call("revise_syllabus", syllabus_id=syllabus_id, based_on_revision=1, **change)
    assert revised.output == {"syllabus_id": syllabus_id, "revision": 2}

    stale = await call("revise_syllabus", syllabus_id=syllabus_id, based_on_revision=1, **change)
    assert stale.is_error
    assert "StaleRevision" in stale.output


async def test_get_and_list_syllabi(call):
    syllabus_id = (await call("create_syllabus", **PLAN)).output["syllabus_id"]

    got = await call("get_syllabus", syllabus_id=syllabus_id)
    assert got.output["id"] == syllabus_id
    assert got.output["units"][0]["objectives"] == [{"id": "basics_obj", "text": "Can do basics"}]

    listed = await call("list_syllabi")
    assert listed.output == {
        "syllabi": [
            {"syllabus_id": syllabus_id, "topic": "Python", "goal": PLAN["goal"], "revision": 1}
        ]
    }

    missing = await call("get_syllabus", syllabus_id="syl_nope")
    assert missing.is_error
    assert "no syllabus 'syl_nope'" in missing.output


async def test_create_quiz_assigns_the_id_and_checks_tags(call, db: Database):
    syllabus_id = (await call("create_syllabus", **PLAN)).output["syllabus_id"]

    created = await call(
        "create_quiz",
        title="Checkpoint",
        purpose="checkpoint",
        syllabus_id=syllabus_id,
        questions=tagged("basics_obj"),
    )
    quiz_id = created.output["quiz_id"]
    assert quiz_id.startswith("quiz_")
    assert (await QuizRepo(db).get(LOCAL_LEARNER, quiz_id)).syllabus_id == syllabus_id

    bad = await call(
        "create_quiz",
        title="Checkpoint",
        purpose="checkpoint",
        syllabus_id=syllabus_id,
        questions=tagged("loops_obj"),
    )
    assert bad.is_error
    assert "objective ids not in syllabus" in bad.output


async def test_submit_quiz_answers_grades_and_records_evidence(call, db: Database):
    syllabus_id = (await call("create_syllabus", **PLAN)).output["syllabus_id"]
    quiz_id = (
        await call(
            "create_quiz",
            title="Checkpoint",
            purpose="checkpoint",
            syllabus_id=syllabus_id,
            questions=tagged("basics_obj"),
        )
    ).output["quiz_id"]

    result = await call(
        "submit_quiz_answers",
        quiz_id=quiz_id,
        responses={
            "q1": {"kind": "choice", "option_ids": ["a"]},
            "q2": {"kind": "number", "value": 4},
        },
    )
    assert result.output["attempt_id"].startswith("att_")
    assert result.output["correct"] == 1
    assert result.output["total"] == 2
    assert result.output["results"] == [
        {"question_id": "q1", "correct": True},
        {"question_id": "q2", "correct": False},
    ]
    evidence = await EvidenceRepo(db).for_syllabus(LOCAL_LEARNER, syllabus_id)
    assert {e.attempt_id for e in evidence} == {result.output["attempt_id"]}


async def test_an_answer_of_the_wrong_kind_comes_back_as_an_error(call):
    quiz_id = (
        await call("create_quiz", title="Placement", purpose="placement", questions=QUESTIONS)
    ).output["quiz_id"]
    result = await call(
        "submit_quiz_answers", quiz_id=quiz_id, responses={"q2": {"kind": "text", "text": "3"}}
    )
    assert result.is_error
    assert "needs a NumberResponse, got TextResponse" in result.output
