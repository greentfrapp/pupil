from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pupil_server.agents import ToolResult
from pupil_server.db import LOCAL_LEARNER, Database
from pupil_server.db.learning import AttemptRepo, LessonRepo, SyllabusRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.lesson import Answer, Attempt, NumberResponse, TeachCard
from pupil_server.learning.tools import learning_tools
from pupil_server.learning.topic import Profile


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
        "explanation": "def is short for define.",
        "options": [{"id": "a", "text": "def"}, {"id": "b", "text": "fun"}],
        "correct": ["a"],
    },
    {
        "kind": "numeric",
        "id": "q2",
        "prompt": "len('abc')?",
        "difficulty": 1,
        "explanation": "Three characters.",
        "answer": 3,
    },
]


def tagged(objective_id: str) -> list[dict]:
    return [{**q, "objective_ids": [objective_id]} for q in QUESTIONS]


async def create(call) -> dict:
    """A stored syllabus, as the agent sees it."""
    return (await call("create_syllabus", **PLAN)).output["syllabus"]


def objective_id(syllabus: dict, unit_id: str) -> str:
    unit = next(u for u in syllabus["units"] if u["id"] == unit_id)
    return unit["objectives"][0]["id"]


async def create_lesson(call, syllabus: dict, unit_id: str) -> str:
    created = await call(
        "create_lesson",
        title="Basics",
        purpose="lesson",
        syllabus_id=syllabus["id"],
        items=tagged(objective_id(syllabus, unit_id)),
    )
    return created.output["lesson_id"]


async def take(db: Database, lesson_id: str, attempt_id: str = "att_1", **answers) -> None:
    """Submit an attempt at the lesson, skipping any question not given an answer."""
    skipped = Answer(response=None, correct=False)
    attempt = Attempt(
        id=attempt_id,
        lesson_id=lesson_id,
        answers={"q1": skipped, "q2": skipped, **answers},
        submitted_at=datetime.now(UTC),
    )
    await AttemptRepo(db).submit(LOCAL_LEARNER, attempt)


async def practise(call, db: Database, syllabus: dict, unit_id: str) -> None:
    """Give the learner evidence on a unit's objective."""
    await take(db, await create_lesson(call, syllabus, unit_id))


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


# Lessons

CARD = {"kind": "teach_card", "id": "c1", "title": "Functions", "text": "def names a function."}


async def test_create_lesson_stores_it_with_an_assigned_id(call, db: Database):
    syllabus = await create(call)
    created = await call(
        "create_lesson",
        title="Functions",
        purpose="lesson",
        syllabus_id=syllabus["id"],
        keep_order=True,
        items=[CARD, *tagged(objective_id(syllabus, "basics"))],
    )
    lesson_id = created.output["lesson_id"]
    assert lesson_id.startswith("les_")

    stored = await LessonRepo(db).get(LOCAL_LEARNER, lesson_id)
    assert stored.syllabus_id == syllabus["id"]
    assert stored.keep_order
    assert isinstance(stored.items[0], TeachCard)
    assert [q.id for q in stored.questions] == ["q1", "q2"]


async def test_create_lesson_checks_tags(call):
    syllabus = await create(call)
    bad = await call(
        "create_lesson",
        title="Functions",
        purpose="lesson",
        syllabus_id=syllabus["id"],
        items=tagged("obj_unknown"),
    )
    assert bad.is_error
    assert "objective ids not in syllabus" in bad.output


async def test_an_invalid_lesson_comes_back_as_an_error(call):
    result = await call(
        "create_lesson", title="Placement", purpose="placement", items=[CARD, *QUESTIONS]
    )
    assert result.is_error
    assert "a placement lesson measures, so has no teach cards" in result.output


async def test_recent_results_describe_the_latest_attempts(call, db: Database):
    syllabus = await create(call)
    lesson_id = await create_lesson(call, syllabus, "basics")
    await take(db, lesson_id, "att_1", q2=Answer(response=NumberResponse(value=4), correct=False))
    await take(db, lesson_id, "att_2", q2=Answer(response=NumberResponse(value=3), correct=True))

    result = await call("recent_results", limit=1)
    [latest] = result.output["attempts"]
    assert latest["summary"].splitlines() == [
        f"'Basics' ({lesson_id}), attempt 2: 1 of 2 right.",
        "- q1: wrong, skipped",
        "- q2: right",
    ]


# For a topic


@pytest.fixture
async def topic_id(db: Database) -> str:
    profile = Profile(why="work", depth="working", level="basics")
    return (await TopicRepo(db).create(LOCAL_LEARNER, "Python", profile)).id


@pytest.fixture
def call_for_topic(db: Database, topic_id: str):
    tools = {t.name: t for t in learning_tools(db, LOCAL_LEARNER, topic_id)}

    async def call(name: str, **arguments: Any) -> ToolResult:
        return await tools[name].invoke("call_1", arguments)

    return call


async def test_what_a_topics_run_creates_is_filed_under_the_topic(
    call_for_topic, db: Database, topic_id: str
):
    syllabus = await create(call_for_topic)
    lesson_id = await create_lesson(call_for_topic, syllabus, "basics")
    assert (await SyllabusRepo(db).for_topic(LOCAL_LEARNER, topic_id)).id == syllabus["id"]
    assert await LessonRepo(db).topic_of(LOCAL_LEARNER, lesson_id) == topic_id


async def test_a_topics_run_can_keep_notes_and_read_past_lessons(
    call_for_topic, db: Database, topic_id: str
):
    noted = await call_for_topic("add_note", text="prefers real-world examples")
    assert not noted.is_error
    notes = await TopicRepo(db).notes(LOCAL_LEARNER, topic_id)
    assert [n.text for n in notes] == ["prefers real-world examples"]

    lesson_id = await create_lesson(call_for_topic, await create(call_for_topic), "basics")
    read = await call_for_topic("get_lesson", lesson_id=lesson_id)
    assert [q["id"] for q in read.output["items"]] == ["q1", "q2"]


def test_only_a_topics_run_gets_note_and_lesson_reading_tools(db: Database, topic_id: str):
    chat = {t.name for t in learning_tools(db, LOCAL_LEARNER)}
    run = {t.name for t in learning_tools(db, LOCAL_LEARNER, topic_id)}
    assert run - chat == {"add_note", "get_lesson"}
    assert chat - run == {"list_syllabi"}
