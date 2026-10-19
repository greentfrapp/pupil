from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pupil_server.agents import ToolResult
from pupil_server.db import LOCAL_LEARNER, Database
from pupil_server.db.learning import AttemptRepo, QuizRepo, SyllabusRepo
from pupil_server.learning.quiz import QuizAttempt
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
        "objectives": [{"text": f"Can do {uid}"}],
        "prerequisites": list(prerequisites),
    }


PLAN = {"topic": "Python", "goal": "Write small scripts", "units": [unit("basics"), unit("loops")]}

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


async def create(call) -> dict:
    """A stored syllabus, as the agent sees it."""
    return (await call("create_syllabus", **PLAN)).output["syllabus"]


def objective_id(syllabus: dict, unit_id: str) -> str:
    unit = next(u for u in syllabus["units"] if u["id"] == unit_id)
    return unit["objectives"][0]["id"]


async def practise(call, db: Database, syllabus: dict, unit_id: str) -> None:
    """Give the learner evidence on a unit's objective."""
    quiz = await call(
        "create_quiz",
        title="Checkpoint",
        purpose="checkpoint",
        syllabus_id=syllabus["id"],
        questions=tagged(objective_id(syllabus, unit_id)),
    )
    attempt = QuizAttempt(
        id="att_1", quiz_id=quiz.output["quiz_id"], responses={}, submitted_at=datetime.now(UTC)
    )
    await AttemptRepo(db).submit(LOCAL_LEARNER, attempt)


async def revise(call, syllabus: dict, units: list[dict], **extra: Any) -> ToolResult:
    return await call(
        "revise_syllabus",
        syllabus_id=syllabus["id"],
        based_on_revision=syllabus["revision"],
        topic=syllabus["topic"],
        goal=syllabus["goal"],
        units=units,
        **extra,
    )


# Syllabi


async def test_create_syllabus_assigns_the_ids(call, db: Database):
    result = await call("create_syllabus", **PLAN)
    assert not result.is_error
    syllabus = result.output["syllabus"]
    assert syllabus["id"].startswith("syl_")
    assert syllabus["revision"] == 1
    assert objective_id(syllabus, "basics").startswith("obj_")
    stored = await SyllabusRepo(db).get(LOCAL_LEARNER, syllabus["id"])
    assert stored.model_dump(mode="json") == syllabus


async def test_create_syllabus_refuses_objective_ids(call):
    with_id = {**unit("basics"), "objectives": [{"id": "basics_obj", "text": "Can do basics"}]}
    result = await call("create_syllabus", **{**PLAN, "units": [with_id]})
    assert result.is_error
    assert "invalid arguments" in result.output


async def test_an_invalid_syllabus_comes_back_as_an_error(call, db: Database):
    result = await call("create_syllabus", **{**PLAN, "units": [unit("a", "b"), unit("b", "a")]})
    assert result.is_error
    assert "prerequisite cycle: a -> b -> a" in result.output
    assert await SyllabusRepo(db).list_latest(LOCAL_LEARNER) == []


async def test_revise_syllabus_needs_the_revision_it_was_based_on(call):
    syllabus = await create(call)
    revised = await revise(call, syllabus, syllabus["units"])
    assert revised.output["syllabus"]["revision"] == 2

    stale = await revise(call, syllabus, syllabus["units"])
    assert stale.is_error
    assert "StaleRevision" in stale.output


async def test_revise_reports_added_reworded_and_removed_objectives(call):
    syllabus = await create(call)
    basics, loops = syllabus["units"]
    reworded = {**basics, "objectives": [{**basics["objectives"][0], "text": "Use variables"}]}
    added = unit("functions")

    result = await revise(call, syllabus, [reworded, added])
    assert not result.is_error
    changes = result.output["changes"]
    new_id = objective_id(result.output["syllabus"], "functions")
    assert changes["added"] == [{"id": new_id, "text": "Can do functions"}]
    assert changes["reworded"] == [
        {
            "id": objective_id(syllabus, "basics"),
            "before": "Can do basics",
            "after": "Use variables",
        }
    ]
    assert changes["removed"] == [loops["objectives"][0]]
    assert result.output["warnings"] == []  # no progress on either yet


async def test_rewording_an_objective_with_progress_warns(call, db: Database):
    syllabus = await create(call)
    await practise(call, db, syllabus, "basics")
    basics, loops = syllabus["units"]
    reworded = {**basics, "objectives": [{**basics["objectives"][0], "text": "Use variables"}]}

    result = await revise(call, syllabus, [reworded, loops])
    assert not result.is_error
    [warning] = result.output["warnings"]
    assert objective_id(syllabus, "basics") in warning
    assert "If it is no longer the same skill" in warning


async def test_dropping_an_objective_with_progress_must_be_retired(call, db: Database):
    syllabus = await create(call)
    await practise(call, db, syllabus, "loops")
    basics, _ = syllabus["units"]
    loops_id = objective_id(syllabus, "loops")

    refused = await revise(call, syllabus, [basics])
    assert refused.is_error
    assert f"progress on objectives missing from this revision: {loops_id}" in refused.output
    assert (await SyllabusRepo(db).get(LOCAL_LEARNER, syllabus["id"])).revision == 1

    retired = await revise(call, syllabus, [basics], retired_objectives=[loops_id])
    assert not retired.is_error
    assert retired.output["changes"]["removed"] == [syllabus["units"][1]["objectives"][0]]


async def test_dropping_an_objective_without_progress_needs_no_retiring(call):
    syllabus = await create(call)
    result = await revise(call, syllabus, syllabus["units"][:1])
    assert not result.is_error


async def test_revise_refuses_unknown_and_contradictory_objective_ids(call):
    syllabus = await create(call)
    basics, loops = syllabus["units"]
    invented = {**loops, "objectives": [{"id": "obj_invented", "text": "Can do loops"}]}

    unknown = await revise(call, syllabus, [basics, invented])
    assert unknown.is_error
    assert "objective ids not in revision 1: ['obj_invented']" in unknown.output

    basics_id = objective_id(syllabus, "basics")
    contradictory = await revise(call, syllabus, [basics, loops], retired_objectives=[basics_id])
    assert contradictory.is_error
    assert f"retired objectives are still in the syllabus: ['{basics_id}']" in contradictory.output


async def test_get_and_list_syllabi(call):
    syllabus = await create(call)

    got = await call("get_syllabus", syllabus_id=syllabus["id"])
    assert got.output == syllabus

    listed = await call("list_syllabi")
    assert listed.output == {
        "syllabi": [
            {"syllabus_id": syllabus["id"], "topic": "Python", "goal": PLAN["goal"], "revision": 1}
        ]
    }

    missing = await call("get_syllabus", syllabus_id="syl_nope")
    assert missing.is_error
    assert "no syllabus 'syl_nope'" in missing.output


# Quizzes


async def test_create_quiz_assigns_the_id_and_checks_tags(call, db: Database):
    syllabus = await create(call)

    created = await call(
        "create_quiz",
        title="Checkpoint",
        purpose="checkpoint",
        syllabus_id=syllabus["id"],
        questions=tagged(objective_id(syllabus, "basics")),
    )
    quiz_id = created.output["quiz_id"]
    assert quiz_id.startswith("quiz_")
    assert (await QuizRepo(db).get(LOCAL_LEARNER, quiz_id)).syllabus_id == syllabus["id"]

    bad = await call(
        "create_quiz",
        title="Checkpoint",
        purpose="checkpoint",
        syllabus_id=syllabus["id"],
        questions=tagged("obj_unknown"),
    )
    assert bad.is_error
    assert "objective ids not in syllabus" in bad.output
