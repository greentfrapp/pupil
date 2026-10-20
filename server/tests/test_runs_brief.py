from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pupil_server.db import LOCAL_LEARNER, Database
from pupil_server.db.learning import AttemptRepo, LessonRepo, SyllabusRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.lesson import Answer, Attempt, BoolResponse, Lesson, TrueFalse
from pupil_server.learning.syllabus import Syllabus
from pupil_server.learning.topic import Profile, Topic
from pupil_server.runs.brief import build_brief
from pupil_server.runs.jobs import INSTRUCTIONS

ME = LOCAL_LEARNER
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path: Path):
    db = await Database.open(tmp_path / "pupil.db")
    yield db
    await db.close()


@pytest.fixture
async def topic(db: Database) -> Topic:
    profile = Profile(why="exam", depth="expert", level="well", specific="AP Calculus BC")
    return await TopicRepo(db).create(ME, "Calculus", profile)


def sections(brief: str) -> dict[str, str]:
    """The brief's sections by heading."""
    parts = [p.split("\n", 1) for p in brief.split("\n\n# ")]
    return {head.removeprefix("# "): body for head, body in parts}


async def test_a_first_brief_has_the_job_and_the_setup_answers(db: Database, topic: Topic):
    brief = sections(await build_brief(db, ME, topic, "placement", None))
    assert brief["Your job"] == INSTRUCTIONS["placement"]
    assert brief["The topic"].splitlines() == [
        "The learner asked to learn: 'Calculus'",
        "- Why: for a course or exam (exam)",
        "- How far: deep expertise (expert)",
        "- Knows already: knows it well (well)",
        "- Anything specific: AP Calculus BC",
    ]
    assert brief["Your notes"] == "None yet."
    assert brief["The syllabus"] == "None yet."
    assert brief["Results since your last run"] == "None."
    assert brief["Recent lessons, oldest first"] == "None yet."


async def test_a_later_brief_has_notes_the_syllabus_and_results_since_the_last_run(
    db: Database, topic: Topic
):
    await TopicRepo(db).add_note(ME, topic.id, "rushes through limits")
    unit = {"id": "u1", "title": "U", "summary": "", "objectives": [{"id": "o1", "text": "t"}]}
    await SyllabusRepo(db).create(
        ME, Syllabus(id="syl_1", topic="C", goal="g", units=[unit]), topic.id
    )
    question = TrueFalse(
        id="q1", prompt="p", difficulty=1, explanation="e", answer=True, objective_ids=["o1"]
    )
    lessons, attempts = LessonRepo(db), AttemptRepo(db)
    for lid in ("les_1", "les_2"):
        lesson = Lesson(id=lid, title=lid, purpose="lesson", syllabus_id="syl_1", items=[question])
        await lessons.create(ME, lesson, topic.id)

    def attempt(aid: str, at: datetime, correct: bool) -> Attempt:
        answer = Answer(response=BoolResponse(value=correct), correct=correct)
        return Attempt(id=aid, lesson_id="les_1", answers={"q1": answer}, submitted_at=at)

    await attempts.submit(ME, attempt("att_before", T0, False))
    await attempts.submit(ME, attempt("att_after", T0 + timedelta(hours=2), True))

    brief = sections(await build_brief(db, ME, topic, "next_lesson", T0 + timedelta(hours=1)))
    assert brief["Your notes"] == "- rushes through limits"
    assert '"id": "syl_1"' in brief["The syllabus"]
    assert (
        brief["Results since your last run"]
        == "'les_1' (les_1), attempt 2: 1 of 1 right.\n- q1: right"
    )
    assert brief["Recent lessons, oldest first"].splitlines() == [
        "- 'les_1' (les_1, lesson, 1 questions): taken 2 times, latest 1 of 1 right",
        "- 'les_2' (les_2, lesson, 1 questions): not taken yet",
    ]
