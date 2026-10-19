import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pupil_server.db import LOCAL_LEARNER, AlreadyExists, Database, NotFound
from pupil_server.db.learning import (
    AttemptRepo,
    EvidenceRepo,
    QuizRepo,
    StaleRevision,
    SyllabusRepo,
)
from pupil_server.learning.quiz import (
    BoolResponse,
    ChoiceResponse,
    MultipleChoice,
    Quiz,
    QuizAttempt,
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


def quiz(qid: str = "quiz_1", syllabus_id: str | None = "syl_1", tags=("o1", "o2")) -> Quiz:
    tagged = syllabus_id is not None
    return Quiz(
        id=qid,
        title="Check",
        purpose="checkpoint" if tagged else "placement",
        syllabus_id=syllabus_id,
        questions=[
            MultipleChoice(
                id="q1",
                prompt="Pick",
                difficulty=1,
                options=[{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
                correct=["a"],
                objective_ids=[tags[0]] if tagged else [],
            ),
            TrueFalse(
                id="q2",
                prompt="True?",
                difficulty=2,
                answer=True,
                objective_ids=list(tags) if tagged else [],
            ),
        ],
    )


def attempt(aid: str = "att_1", quiz_id: str = "quiz_1", at: datetime = T0, **responses):
    return QuizAttempt(id=aid, quiz_id=quiz_id, responses=responses, submitted_at=at)


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


async def test_list_latest(db: Database):
    repo = SyllabusRepo(db)
    await repo.create(ME, syllabus("syl_a"))
    await repo.create(ME, syllabus("syl_b"))
    await repo.revise(ME, syllabus("syl_a", goal="revised"))
    await repo.create(OTHER, syllabus("syl_c"))
    listed = await repo.list_latest(ME)
    assert [(s.id, s.revision) for s in listed] == [("syl_a", 2), ("syl_b", 1)]


async def test_another_learners_records_are_not_found(db: Database):
    syllabi, quizzes, attempts = SyllabusRepo(db), QuizRepo(db), AttemptRepo(db)
    await syllabi.create(ME, syllabus())
    await quizzes.create(ME, quiz())
    await attempts.submit(ME, attempt(q1=ChoiceResponse(option_ids=["a"])))
    with pytest.raises(NotFound):
        await syllabi.get(OTHER, "syl_1")
    with pytest.raises(NotFound):
        await syllabi.revise(OTHER, syllabus())
    with pytest.raises(NotFound):
        await quizzes.get(OTHER, "quiz_1")
    with pytest.raises(NotFound):
        await quizzes.create(OTHER, quiz("quiz_2"))  # can't build on someone else's syllabus
    with pytest.raises(NotFound):
        await attempts.submit(OTHER, attempt("att_2"))
    with pytest.raises(NotFound):
        await attempts.get(OTHER, "att_1")


# Quizzes


async def test_quiz_round_trip(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    repo = QuizRepo(db)
    await repo.create(ME, quiz())
    await repo.create(ME, quiz("quiz_p", syllabus_id=None))
    assert await repo.get(ME, "quiz_1") == quiz()
    assert await repo.get(ME, "quiz_p") == quiz("quiz_p", syllabus_id=None)
    with pytest.raises(AlreadyExists, match="quiz 'quiz_1' already exists"):
        await repo.create(ME, quiz())


async def test_quiz_tags_are_checked_against_the_latest_revision(db: Database):
    syllabi, repo = SyllabusRepo(db), QuizRepo(db)
    await syllabi.create(ME, syllabus())
    with pytest.raises(NotFound, match="no syllabus 'syl_9'"):
        await repo.create(ME, quiz(syllabus_id="syl_9"))
    with pytest.raises(ValueError, match=re.escape("not in syllabus 'syl_1': ['o9']")):
        await repo.create(ME, quiz(tags=("o1", "o9")))

    # Revision 2 drops o2, so a quiz still testing it is refused.
    revised = syllabus().model_copy(update={"units": syllabus().units[:1]})
    await syllabi.revise(ME, revised)
    with pytest.raises(ValueError, match=re.escape("['o2']")):
        await repo.create(ME, quiz())
    with pytest.raises(NotFound):
        await repo.get(ME, "quiz_1")  # nothing was stored


# Attempts and evidence


async def test_submit_stores_the_attempt_results_and_evidence(db: Database):
    await SyllabusRepo(db).create(ME, syllabus())
    await QuizRepo(db).create(ME, quiz())
    attempts = AttemptRepo(db)
    sent = attempt(q1=ChoiceResponse(option_ids=["a"]), q2=BoolResponse(value=False))

    results = await attempts.submit(ME, sent)
    assert [(r.question_id, r.correct) for r in results] == [("q1", True), ("q2", False)]
    assert await attempts.get(ME, "att_1") == sent
    assert await attempts.results(ME, "att_1") == results

    evidence = await EvidenceRepo(db).for_syllabus(ME, "syl_1")
    assert [(e.objective_id, e.question_id, e.correct) for e in evidence] == [
        ("o1", "q1", True),
        ("o1", "q2", False),
        ("o2", "q2", False),
    ]
    assert {(e.attempt_id, e.at) for e in evidence} == {("att_1", T0)}


async def test_evidence_is_oldest_first_and_per_syllabus(db: Database):
    syllabi, quizzes, attempts = SyllabusRepo(db), QuizRepo(db), AttemptRepo(db)
    await syllabi.create(ME, syllabus())
    await syllabi.create(ME, syllabus("syl_2"))
    await quizzes.create(ME, quiz())
    await quizzes.create(ME, quiz("quiz_2", syllabus_id="syl_2"))
    later = T0 + timedelta(days=1)
    await attempts.submit(ME, attempt("att_late", at=later, q1=ChoiceResponse(option_ids=["b"])))
    await attempts.submit(ME, attempt("att_early", q1=ChoiceResponse(option_ids=["a"])))
    await attempts.submit(ME, attempt("att_other", "quiz_2", q2=BoolResponse(value=True)))

    evidence = await EvidenceRepo(db).for_syllabus(ME, "syl_1")
    assert [e.attempt_id for e in evidence if e.question_id == "q1"] == ["att_early", "att_late"]
    assert "att_other" not in {e.attempt_id for e in evidence}


async def test_placement_quiz_results_give_no_evidence(db: Database):
    await QuizRepo(db).create(ME, quiz("quiz_p", syllabus_id=None))
    attempts = AttemptRepo(db)
    results = await attempts.submit(ME, attempt(quiz_id="quiz_p", q2=BoolResponse(value=True)))
    assert [(r.question_id, r.correct) for r in results] == [("q1", False), ("q2", True)]
    assert await attempts.results(ME, "att_1") == results
    rows = await db.run(lambda c: c.execute("SELECT count(*) FROM evidence").fetchone()[0])
    assert rows == 0


async def test_a_rejected_attempt_stores_nothing(db: Database):
    await QuizRepo(db).create(ME, quiz("quiz_p", syllabus_id=None))
    attempts = AttemptRepo(db)
    with pytest.raises(ValueError, match="not in quiz"):
        await attempts.submit(ME, attempt(quiz_id="quiz_p", q9=BoolResponse(value=True)))
    with pytest.raises(NotFound):
        await attempts.get(ME, "att_1")

    await attempts.submit(ME, attempt(quiz_id="quiz_p"))
    with pytest.raises(AlreadyExists, match="attempt 'att_1' already exists"):
        await attempts.submit(ME, attempt(quiz_id="quiz_p"))
