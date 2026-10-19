from pathlib import Path

import pytest

from pupil_server.agents import TextDelta, ToolCall, TurnComplete
from pupil_server.conversations.transcript import UserMessage
from pupil_server.db import LOCAL_LEARNER, Database, NotFound
from pupil_server.db.conversations import ConversationRepo

ME = LOCAL_LEARNER
OTHER = "lrn_other"


@pytest.fixture
async def db(tmp_path: Path):
    db = await Database.open(tmp_path / "pupil.db")
    await db.run(
        lambda c: c.execute("INSERT INTO learners (id, created_at) VALUES (?, 'x')", (OTHER,))
    )
    yield db
    await db.close()


@pytest.fixture
def repo(db: Database) -> ConversationRepo:
    return ConversationRepo(db)


async def test_create_and_list(repo: ConversationRepo):
    first = await repo.create(ME)
    second = await repo.create(ME)
    await repo.create(OTHER)
    assert first.id.startswith("conv_")
    assert await repo.get(ME, first.id) == first
    assert await repo.list_recent(ME) == [second, first]


async def test_transcript_keeps_order_and_item_types(repo: ConversationRepo):
    conversation = await repo.create(ME)
    items = [
        UserMessage(text="hi"),
        TextDelta(text="Hello there"),
        ToolCall(id="c1", name="get_current_time", input={}),
        TurnComplete(cost_usd=0.01),
    ]
    for item in items:
        await repo.append(ME, conversation.id, item)
    assert await repo.transcript(ME, conversation.id) == items


async def test_the_latest_resume_token_per_backend_wins(repo: ConversationRepo):
    conversation = await repo.create(ME)
    assert await repo.resume_token(ME, conversation.id, "claude") is None

    await repo.save_resume_token(ME, conversation.id, "claude", "t1")
    await repo.save_resume_token(ME, conversation.id, "claude", "t2")
    await repo.save_resume_token(ME, conversation.id, "fake", "f1")
    assert await repo.resume_token(ME, conversation.id, "claude") == "t2"
    assert await repo.resume_token(ME, conversation.id, "fake") == "f1"


async def test_an_unchanged_resume_token_is_not_saved_again(repo: ConversationRepo, db: Database):
    conversation = await repo.create(ME)
    await repo.save_resume_token(ME, conversation.id, "claude", "t1")
    await repo.save_resume_token(ME, conversation.id, "claude", "t1")
    rows = await db.run(lambda c: c.execute("SELECT count(*) FROM resume_tokens").fetchone()[0])
    assert rows == 1


async def test_another_learners_conversation_is_not_found(repo: ConversationRepo):
    conversation = await repo.create(ME)
    with pytest.raises(NotFound):
        await repo.get(OTHER, conversation.id)
    with pytest.raises(NotFound):
        await repo.append(OTHER, conversation.id, UserMessage(text="hi"))
    with pytest.raises(NotFound):
        await repo.transcript(OTHER, conversation.id)
    with pytest.raises(NotFound):
        await repo.save_resume_token(OTHER, conversation.id, "claude", "t")
    with pytest.raises(NotFound):
        await repo.resume_token(OTHER, conversation.id, "claude")
