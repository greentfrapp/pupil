from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pupil_server.db import LOCAL_LEARNER, Database, NotFound
from pupil_server.db.learning import AttemptRepo, LessonRepo, SyllabusRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.lesson import Answer, Attempt, Lesson, TrueFalse
from pupil_server.learning.syllabus import Syllabus
from pupil_server.learning.topic import Profile

ME = LOCAL_LEARNER
OTHER = "lrn_other"
PROFILE = Profile(why="work", depth="working", level="basics", specific="BigQuery")
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path: Path):
    db = await Database.open(tmp_path / "pupil.db")
    await db.run(
        lambda c: c.execute("INSERT INTO learners (id, created_at) VALUES (?, 'x')", (OTHER,))
    )
    yield db
    await db.close()


def syllabus(sid: str = "syl_1") -> Syllabus:
    unit = {"id": "u1", "title": "U", "summary": "", "objectives": [{"id": "o1", "text": "t"}]}
    return Syllabus(id=sid, topic="SQL", goal="g", units=[unit])


def lesson(lid: str) -> Lesson:
    question = TrueFalse(id="q1", prompt="p", difficulty=1, explanation="e", answer=True)
    return Lesson(id=lid, title=lid, purpose="placement", items=[question])


def attempt(aid: str, lesson_id: str, at: datetime) -> Attempt:
    answers = {"q1": Answer(response=None, correct=False)}
    return Attempt(id=aid, lesson_id=lesson_id, answers=answers, submitted_at=at)


# Topics and notes


async def test_topics_are_stored_and_listed_newest_first(db: Database):
    repo = TopicRepo(db)
    first = await repo.create(ME, "SQL for data analysis", PROFILE)
    second = await repo.create(ME, "Spanish", PROFILE)
    await repo.create(OTHER, "Chess", PROFILE)
    assert await repo.get(ME, first.id) == first
    assert [t.id for t in await repo.list_recent(ME)] == [second.id, first.id]


async def test_notes_are_kept_per_topic_oldest_first(db: Database):
    repo = TopicRepo(db)
    sql, spanish = await repo.create(ME, "SQL", PROFILE), await repo.create(ME, "Spanish", PROFILE)
    await repo.add_note(ME, sql.id, "prefers real-world examples")
    await repo.add_note(ME, sql.id, "mixes up joins and unions")
    await repo.add_note(ME, spanish.id, "knows French")
    assert [n.text for n in await repo.notes(ME, sql.id)] == [
        "prefers real-world examples",
        "mixes up joins and unions",
    ]


async def test_another_learners_topic_is_not_found(db: Database):
    repo = TopicRepo(db)
    topic = await repo.create(ME, "SQL", PROFILE)
    with pytest.raises(NotFound):
        await repo.get(OTHER, topic.id)
    with pytest.raises(NotFound):
        await repo.add_note(OTHER, topic.id, "x")
    with pytest.raises(NotFound):
        await LessonRepo(db).create(OTHER, lesson("les_1"), topic.id)
    with pytest.raises(NotFound):
        await SyllabusRepo(db).create(OTHER, syllabus(), topic.id)


# What belongs to a topic


async def test_a_topics_plan_is_its_newest_syllabus_at_its_latest_revision(db: Database):
    topic = await TopicRepo(db).create(ME, "SQL", PROFILE)
    syllabi = SyllabusRepo(db)
    assert await syllabi.for_topic(ME, topic.id) is None
    await syllabi.create(ME, syllabus("syl_old"), topic.id)
    await syllabi.create(ME, syllabus("syl_new"), topic.id)
    await syllabi.create(ME, syllabus("syl_elsewhere"))
    await syllabi.revise(ME, syllabus("syl_new"))
    plan = await syllabi.for_topic(ME, topic.id)
    assert (plan.id, plan.revision) == ("syl_new", 2)


async def test_a_topics_lessons_are_listed_oldest_first(db: Database):
    topic = await TopicRepo(db).create(ME, "SQL", PROFILE)
    lessons = LessonRepo(db)
    await lessons.create(ME, lesson("les_1"), topic.id)
    await lessons.create(ME, lesson("les_no_topic"))
    await lessons.create(ME, lesson("les_2"), topic.id)
    assert [x.id for x in await lessons.for_topic(ME, topic.id)] == ["les_1", "les_2"]
    assert await lessons.topic_of(ME, "les_1") == topic.id
    assert await lessons.topic_of(ME, "les_no_topic") is None


async def test_attempts_since_a_time_are_the_topics_only(db: Database):
    topic = await TopicRepo(db).create(ME, "SQL", PROFILE)
    lessons, attempts = LessonRepo(db), AttemptRepo(db)
    await lessons.create(ME, lesson("les_1"), topic.id)
    await lessons.create(ME, lesson("les_2"), topic.id)
    await lessons.create(ME, lesson("les_no_topic"))
    await attempts.submit(ME, attempt("att_old", "les_1", T0))
    await attempts.submit(ME, attempt("att_new", "les_2", T0 + timedelta(hours=2)))
    await attempts.submit(ME, attempt("att_no_topic", "les_no_topic", T0 + timedelta(hours=3)))

    since = await attempts.since(ME, topic.id, T0 + timedelta(hours=1))
    assert [g.attempt.id for g in since] == ["att_new"]
    ever = await attempts.since(ME, topic.id, None)
    assert [g.attempt.id for g in ever] == ["att_old", "att_new"]
    recent = await attempts.recent(ME, 10, topic.id)
    assert [g.attempt.id for g in recent] == ["att_new", "att_old"]
