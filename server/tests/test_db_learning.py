import asyncio
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pupil_server.db import LOCAL_LEARNER, AlreadyExists, Database, NotFound
from pupil_server.db.learning import (
    AttemptRepo,
    EvidenceRepo,
    LessonRepo,
    PlacementTaken,
    StaleRevision,
    SyllabusRepo,
)
from pupil_server.learning.lesson import (
    Answer,
    Attempt,
    BoolResponse,
    ChoiceResponse,
    Lesson,
    MultipleChoice,
    TrueFalse,
)
from pupil_server.learning.syllabus import Syllabus

ME = LOCAL_LEARNER
OTHER = "lrn_other"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path: Path):
    db = await Database.open(tmp_path / "pupil.db")
    await db.run(
        lambda c: c.execute("INSERT INTO learners (id, created_at) VALUES (?, 'x')", (OTHER,))
    )
    yield db
    await db.close()


def syllabus(sid: str = "syl_1", goal: str = "Write small scripts", revision: int = 1) -> Syllabus:
    return Syllabus(
        id=sid,
        topic="Python",
        goal=goal,
        revision=revision,
        units=[unit("u1", "o1"), unit("u2", "o2")],
    )


def unit(uid: str, objective_id: str) -> dict:
    return {
        "id": uid,
        "title": uid,
        "summary": "",
        "objectives": [{"id": objective_id, "text": "t"}],
    }


def lesson(lid: str = "les_1", syllabus_id: str | None = "syl_1", tags=("o1", "o2")) -> Lesson:
    tagged = syllabus_id is not None
    return Lesson(
        id=lid,
        title="Check",
        purpose="lesson" if tagged else "placement",
        syllabus_id=syllabus_id,
        items=[
            MultipleChoice(
                id="q1",
                prompt="Pick",
                difficulty=1,
                explanation="A it is.",
                options=[{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
                correct=["a"],
                objective_ids=[tags[0]] if tagged else [],
            ),
            TrueFalse(
                id="q2",
                prompt="True?",
                difficulty=2,
                explanation="It is.",
                answer=True,
                objective_ids=list(tags) if tagged else [],
            ),
        ],
    )


SKIPPED = Answer(response=None, correct=False)


def attempt(aid: str = "att_1", lesson_id: str = "les_1", at: datetime = T0, **answers: Answer):
    """An attempt that skips any question not given an answer."""
    every = {"q1": SKIPPED, "q2": SKIPPED, **answers}
    return Attempt(id=aid, lesson_id=lesson_id, answers=every, submitted_at=at)


def right(response) -> Answer:
    return Answer(response=response, correct=True)


def wrong(response) -> Answer:
    return Answer(response=response, correct=False)


# Syllabi


async def test_syllabus_create_and_get(db: Database):
    repo = SyllabusRepo(db)
    stored = await repo.create(ME, syllabus(revision=7))
    assert stored.revision == 1  # numbering is the repository's job
    assert await repo.get(ME, "syl_1") == stored


async def test_revise_adds_a_revision_and_keeps_the_old_one(db: Database):
    repo = SyllabusRepo(db)
    first = await repo.create(ME, syllabus())
    second = await repo.revise(ME, syllabus(goal="Automate my spreadsheets"))
    assert second.revision == 2
    assert await repo.get(ME, "syl_1") == second
    assert await repo.get(ME, "syl_1", revision=1) == first


async def test_revise_from_a_stale_revision_is_refused(db: Database):
    repo = SyllabusRepo(db)
    await repo.create(ME, syllabus())
    await repo.revise(ME, syllabus(goal="newer"))
    with pytest.raises(
        StaleRevision, match="is at revision 2, but this change is based on revision 1"
    ):
        await repo.revise(ME, syllabus(goal="from a stale copy"))
    assert (await repo.get(ME, "syl_1")).goal == "newer"


async def test_syllabus_ids_are_unique_and_must_exist(db: Database):
    repo = SyllabusRepo(db)
    await repo.create(ME, syllabus())
    with pytest.raises(AlreadyExists, match="revise it instead"):
        await repo.create(ME, syllabus())
    with pytest.raises(NotFound, match="no syllabus 'syl_9'"):
        await repo.revise(ME, syllabus("syl_9"))
    with pytest.raises(NotFound, match="no revision 2 of syllabus 'syl_1'"):
        await repo.get(ME, "syl_1", revision=2)


async def test_another_learners_records_are_not_found(db: Database):
    syllabi, lessons, attempts = SyllabusRepo(db), LessonRepo(db), AttemptRepo(db)
    await syllabi.create(ME, syllabus())
    await lessons.create(ME, lesson())
    await attempts.submit(ME, attempt(q1=right(ChoiceResponse(option_ids=["a"]))))
    with pytest.raises(NotFound):
        await syllabi.get(OTHER, "syl_1")
    with pytest.raises(NotFound):
        await syllabi.revise(OTHER, syllabus())
    with pytest.raises(NotFound):
        await lessons.get(OTHER, "les_1")
    with pytest.raises(NotFound):
        await lessons.create(OTHER, lesson("les_2"))  # can't build on someone else's syllabus
    with pytest.raises(NotFound):
        await attempts.submit(OTHER, attempt("att_2"))
    with pytest.raises(NotFound):
        await attempts.get(OTHER, "att_1")
    with pytest.raises(NotFound):
        await attempts.for_lesson(OTHER, "les_1")
    assert await attempts.recent(OTHER, 10) == []
    assert await EvidenceRepo(db).for_syllabus(OTHER, "syl_1") == []


# Lessons


async def test_lessons_with_and_without_a_syllabus_are_stored(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    repo = LessonRepo(db)
    await repo.create(ME, lesson())
    await repo.create(ME, lesson("les_p", syllabus_id=None))
    assert await repo.get(ME, "les_1") == lesson()
    assert await repo.get(ME, "les_p") == lesson("les_p", syllabus_id=None)


async def test_lesson_ids_are_unique(db: Database):
    repo = LessonRepo(db)
    await repo.create(ME, lesson("les_p", syllabus_id=None))
    with pytest.raises(AlreadyExists, match="lesson 'les_p' already exists"):
        await repo.create(ME, lesson("les_p", syllabus_id=None))


async def test_lesson_for_a_missing_syllabus_is_refused(db: Database):
    with pytest.raises(NotFound, match="no syllabus 'syl_9'"):
        await LessonRepo(db).create(ME, lesson(syllabus_id="syl_9"))


async def test_lesson_tags_are_checked_against_the_latest_revision(db: Database):
    syllabi, repo = SyllabusRepo(db), LessonRepo(db)
    await syllabi.create(ME, syllabus())
    # Revision 2 drops o2, so a lesson still testing it is refused.
    revised = syllabus().model_copy(update={"units": syllabus().units[:1]})
    await syllabi.revise(ME, revised)
    with pytest.raises(ValueError, match=re.escape("not in syllabus 'syl_1': ['o2']")):
        await repo.create(ME, lesson())


# Attempts and evidence


async def test_submit_stores_the_attempt_results_and_evidence(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    await LessonRepo(db).create(ME, lesson())
    attempts = AttemptRepo(db)
    sent = attempt(q1=right(ChoiceResponse(option_ids=["a"])), q2=wrong(BoolResponse(value=False)))

    graded = await attempts.submit(ME, sent)
    assert graded.attempt == sent
    assert graded.number == 1
    assert [(r.question_id, r.correct) for r in graded.results] == [("q1", True), ("q2", False)]
    assert await attempts.get(ME, "att_1") == graded

    evidence = await EvidenceRepo(db).for_syllabus(ME, "syl_1")
    assert [(e.objective_id, e.question_id, e.correct) for e in evidence] == [
        ("o1", "q1", True),
        ("o1", "q2", False),
        ("o2", "q2", False),
    ]
    assert all(e.attempt_id == "att_1" and e.attempt_number == 1 for e in evidence)
    assert all(e.at == T0 for e in evidence)


async def test_grades_are_stored_as_sent_not_regraded(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    await LessonRepo(db).create(ME, lesson())
    # q1's answer is "a"; the player said "b" was right, and that is what's kept.
    sent = attempt(q1=right(ChoiceResponse(option_ids=["b"])))
    graded = await AttemptRepo(db).submit(ME, sent)
    assert graded.results[0].correct


async def test_retries_are_numbered_and_each_gives_evidence(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    await LessonRepo(db).create(ME, lesson())
    attempts = AttemptRepo(db)
    later = T0 + timedelta(minutes=3)
    first = await attempts.submit(ME, attempt("att_1", q1=wrong(ChoiceResponse(option_ids=["b"]))))
    retry = await attempts.submit(
        ME, attempt("att_2", at=later, q1=right(ChoiceResponse(option_ids=["a"])))
    )
    assert (first.number, retry.number) == (1, 2)

    evidence = await EvidenceRepo(db).for_syllabus(ME, "syl_1")
    q1 = [(e.attempt_number, e.correct) for e in evidence if e.question_id == "q1"]
    assert q1 == [(1, False), (2, True)]


async def test_attempts_submitted_together_get_different_numbers(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    await LessonRepo(db).create(ME, lesson())
    attempts = AttemptRepo(db)
    graded = await asyncio.gather(
        attempts.submit(ME, attempt("att_1")), attempts.submit(ME, attempt("att_2"))
    )
    assert sorted(g.number for g in graded) == [1, 2]


async def test_placement_is_taken_once(db: Database):
    await LessonRepo(db).create(ME, lesson("les_p", syllabus_id=None))
    attempts = AttemptRepo(db)
    await attempts.submit(ME, attempt("att_1", "les_p"))
    with pytest.raises(PlacementTaken, match="'les_p' has already been taken"):
        await attempts.submit(ME, attempt("att_2", "les_p"))
    assert [g.attempt.id for g in await attempts.for_lesson(ME, "les_p")] == ["att_1"]


async def test_evidence_is_oldest_first_and_per_syllabus(db: Database):
    syllabi, lessons, attempts = SyllabusRepo(db), LessonRepo(db), AttemptRepo(db)
    await syllabi.create(ME, syllabus())
    await syllabi.create(ME, syllabus("syl_2"))
    await lessons.create(ME, lesson())
    await lessons.create(ME, lesson("les_1b"))
    await lessons.create(ME, lesson("les_2", syllabus_id="syl_2"))
    later = T0 + timedelta(days=1)
    await attempts.submit(
        ME, attempt("att_late", at=later, q1=wrong(ChoiceResponse(option_ids=["b"])))
    )
    await attempts.submit(
        ME, attempt("att_early", "les_1b", q1=right(ChoiceResponse(option_ids=["a"])))
    )
    await attempts.submit(ME, attempt("att_other", "les_2", q2=right(BoolResponse(value=True))))

    evidence = await EvidenceRepo(db).for_syllabus(ME, "syl_1")
    assert [e.attempt_id for e in evidence if e.question_id == "q1"] == ["att_early", "att_late"]
    assert "att_other" not in {e.attempt_id for e in evidence}


async def test_placement_results_give_no_evidence(db: Database):
    await LessonRepo(db).create(ME, lesson("les_p", syllabus_id=None))
    attempts = AttemptRepo(db)
    graded = await attempts.submit(
        ME, attempt(lesson_id="les_p", q2=right(BoolResponse(value=True)))
    )
    assert await attempts.get(ME, "att_1") == graded
    rows = await db.run(lambda c: c.execute("SELECT count(*) FROM evidence").fetchone()[0])
    assert rows == 0


async def test_attempt_with_unknown_questions_is_refused(db: Database):
    await LessonRepo(db).create(ME, lesson("les_p", syllabus_id=None))
    attempts = AttemptRepo(db)
    with pytest.raises(ValueError, match="not in lesson"):
        await attempts.submit(ME, attempt(lesson_id="les_p", q9=right(BoolResponse(value=True))))
    with pytest.raises(NotFound):
        await attempts.get(ME, "att_1")


async def test_attempt_ids_are_unique(db: Database):
    await LessonRepo(db).create(ME, lesson("les_p", syllabus_id=None))
    attempts = AttemptRepo(db)
    await attempts.submit(ME, attempt(lesson_id="les_p"))
    with pytest.raises(AlreadyExists, match="attempt 'att_1' already exists"):
        await attempts.submit(ME, attempt(lesson_id="les_p"))


async def test_attempts_at_a_lesson_are_listed_first_attempt_first(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    await LessonRepo(db).create(ME, lesson())
    await LessonRepo(db).create(ME, lesson("les_2"))
    attempts = AttemptRepo(db)
    assert await attempts.for_lesson(ME, "les_1") == []
    await attempts.submit(ME, attempt("att_1"))
    await attempts.submit(ME, attempt("att_x", "les_2"))
    await attempts.submit(ME, attempt("att_2"))
    assert [g.attempt.id for g in await attempts.for_lesson(ME, "les_1")] == ["att_1", "att_2"]


async def test_recent_attempts_are_newest_first_across_lessons(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    await LessonRepo(db).create(ME, lesson())
    await LessonRepo(db).create(ME, lesson("les_2"))
    attempts = AttemptRepo(db)
    await attempts.submit(ME, attempt("att_1", at=T0))
    await attempts.submit(ME, attempt("att_2", "les_2", at=T0 + timedelta(hours=1)))
    await attempts.submit(ME, attempt("att_3", at=T0 + timedelta(hours=2)))
    recent = await attempts.recent(ME, 2)
    assert [(g.attempt.id, g.number) for g in recent] == [("att_3", 2), ("att_2", 1)]
