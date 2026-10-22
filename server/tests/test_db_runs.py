from pathlib import Path

import pytest

from pupil_server.agents import TextDelta, TurnComplete
from pupil_server.db import LOCAL_LEARNER, Database, NotFound
from pupil_server.db.runs import RunRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.topic import Profile
from pupil_server.runs.log import UserMessage

ME = LOCAL_LEARNER
PROFILE = Profile(why="work", depth="working", level="basics")


@pytest.fixture
async def db(tmp_path: Path):
    db = await Database.open(tmp_path / "pupil.db")
    yield db
    await db.close()


@pytest.fixture
async def topic_id(db: Database) -> str:
    return (await TopicRepo(db).create(ME, "SQL", PROFILE)).id


async def test_a_run_is_logged_and_ended(db: Database, topic_id: str):
    runs = RunRepo(db)
    run = await runs.start(ME, topic_id, "placement")
    assert run.finished_at is None

    await runs.append(ME, run.id, UserMessage(text="the brief"))
    await runs.append(ME, run.id, TextDelta(text="done"))
    await runs.finish(ME, run.id, None, 0.25)

    assert await runs.log(ME, run.id) == [UserMessage(text="the brief"), TextDelta(text="done")]
    ended = await runs.get(ME, run.id)
    assert ended.succeeded
    assert ended.cost_usd == 0.25


async def test_latest_and_latest_success(db: Database, topic_id: str):
    runs = RunRepo(db)
    assert await runs.latest(ME, topic_id) is None
    good = await runs.start(ME, topic_id, "placement")
    await runs.finish(ME, good.id, None, None)
    bad = await runs.start(ME, topic_id, "plan")
    await runs.finish(ME, bad.id, "the run didn't create a syllabus", None)
    cut_off = await runs.start(ME, topic_id, "plan")  # never finished

    assert (await runs.latest(ME, topic_id)).id == cut_off.id
    assert (await runs.latest_success(ME, topic_id)).id == good.id
    assert not (await runs.get(ME, bad.id)).succeeded


async def test_another_learners_run_is_not_found(db: Database, topic_id: str):
    runs = RunRepo(db)
    run = await runs.start(ME, topic_id, "placement")
    await db.run(lambda c: c.execute("INSERT INTO learners (id, created_at) VALUES ('lrn_2', 'x')"))
    with pytest.raises(NotFound):
        await runs.get("lrn_2", run.id)
    with pytest.raises(NotFound):
        await runs.append("lrn_2", run.id, TurnComplete())
    with pytest.raises(NotFound):
        await runs.start("lrn_2", topic_id, "plan")
