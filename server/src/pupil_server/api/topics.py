"""Topics: asking to learn something, and following what the agent prepares for it.

Creating a topic starts the agent's first run in the background, and finishing a lesson
starts the next if the topic needs one; lessons are written ahead along the path. The client
polls a topic to see when the next lesson is ready. Once every lesson on the path is taken,
the topic is finished, and the learner can ask to go further.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field

from pupil_server.db import LOCAL_LEARNER, NotFound
from pupil_server.db.learning import AttemptRepo
from pupil_server.db.runs import RunRepo
from pupil_server.db.topics import TopicRepo
from pupil_server.learning.syllabus import Syllabus
from pupil_server.learning.topic import Profile, Topic
from pupil_server.runs.service import NotFinished, RunGoing, Runs
from pupil_server.runs.state import topic_state

router = APIRouter(prefix="/api/topics", tags=["topics"])

# One learner until remote mode adds accounts.
LEARNER = LOCAL_LEARNER


class TopicIn(BaseModel):
    request: str = Field(min_length=1, max_length=500)
    """What the learner wants to learn, in their words."""
    profile: Profile


class LessonSummary(BaseModel):
    lesson_id: str
    title: str
    purpose: Literal["placement", "lesson"]
    questions: int
    attempts: int
    latest_correct: int | None
    """How many questions the latest attempt got right; None if not taken yet."""


class PathUnit(BaseModel):
    """A unit of the syllabus, with its lessons as stops on the learner's path."""

    unit_id: str
    title: str
    summary: str
    stops: int
    """How many lessons the unit takes."""
    lesson_ids: list[str]
    """The lessons written for it so far, oldest first; the rest of its stops are to come."""


class RunStatus(BaseModel):
    job: str
    state: Literal["running", "done", "failed"]
    error: str | None


class TopicOut(BaseModel):
    id: str
    request: str
    profile: Profile
    created_at: AwareDatetime
    syllabus: Syllabus | None
    lessons: list[LessonSummary]
    """Oldest first."""
    path: list[PathUnit]
    """The syllabus's units in learning order, with their lessons; empty without one."""
    next_lesson_id: str | None
    """The oldest lesson not taken yet, if any."""
    finished: bool
    """Every lesson on the path has been taken."""
    last_run: RunStatus | None


def _runs(request: Request) -> Runs:
    return request.app.state.runs


async def _topic_out(request: Request, topic: Topic) -> TopicOut:
    db = request.app.state.db
    attempts = AttemptRepo(db)
    state = await topic_state(db, LEARNER, topic.id)
    lessons = []
    for lesson in state.lessons:
        taken = await attempts.for_lesson(LEARNER, lesson.id)
        lessons.append(
            LessonSummary(
                lesson_id=lesson.id,
                title=lesson.title,
                purpose=lesson.purpose,
                questions=len(lesson.questions),
                attempts=len(taken),
                latest_correct=taken[-1].correct if taken else None,
            )
        )
    run = await RunRepo(db).latest(LEARNER, topic.id)
    status = None
    if job := _runs(request).running_job(topic.id):
        status = RunStatus(job=job, state="running", error=None)
    elif run is None:
        pass
    elif run.finished_at is None:
        # Not going, but never finished: cut off, e.g. by a restart.
        status = RunStatus(job=run.job, state="failed", error="the run was cut off")
    else:
        outcome = "done" if run.error is None else "failed"
        status = RunStatus(job=run.job, state=outcome, error=run.error)
    return TopicOut(
        id=topic.id,
        request=topic.request,
        profile=topic.profile,
        created_at=topic.created_at,
        syllabus=state.syllabus,
        lessons=lessons,
        path=[
            PathUnit(
                unit_id=p.unit.id,
                title=p.unit.title,
                summary=p.unit.summary,
                stops=p.stops,
                lesson_ids=[lesson.id for lesson in p.lessons],
            )
            for p in state.path
        ],
        next_lesson_id=state.untaken[0].id if state.untaken else None,
        finished=state.finished,
        last_run=status,
    )


async def _get(request: Request, topic_id: str) -> Topic:
    try:
        return await TopicRepo(request.app.state.db).get(LEARNER, topic_id)
    except NotFound:
        raise HTTPException(404, "no such topic") from None


@router.post("", status_code=201)
async def create_topic(body: TopicIn, request: Request) -> TopicOut:
    """Start a topic, and the agent's first run for it."""
    topic = await TopicRepo(request.app.state.db).create(LEARNER, body.request, body.profile)
    await _runs(request).prepare(LEARNER, topic.id)
    return await _topic_out(request, topic)


@router.get("")
async def list_topics(request: Request) -> list[TopicOut]:
    """The learner's topics, newest first."""
    topics = await TopicRepo(request.app.state.db).list_recent(LEARNER)
    return [await _topic_out(request, t) for t in topics]


@router.get("/{topic_id}")
async def get_topic(topic_id: str, request: Request) -> TopicOut:
    return await _topic_out(request, await _get(request, topic_id))


@router.post("/{topic_id}/prepare", status_code=202)
async def prepare(topic_id: str, request: Request) -> TopicOut:
    """Start the run the topic needs, if none is going and it needs one, e.g. to try again
    after a run failed."""
    topic = await _get(request, topic_id)
    await _runs(request).prepare(LEARNER, topic.id)
    return await _topic_out(request, topic)


@router.post("/{topic_id}/extend", status_code=202)
async def extend(topic_id: str, request: Request) -> TopicOut:
    """Go further than a finished topic's path: a run adds units, and their lessons follow."""
    topic = await _get(request, topic_id)
    try:
        await _runs(request).extend(LEARNER, topic.id)
    except RunGoing:
        raise HTTPException(409, "the topic already has a run going") from None
    except NotFinished:
        raise HTTPException(409, "the topic isn't finished yet") from None
    return await _topic_out(request, topic)
