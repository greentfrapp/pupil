"""Taking a lesson: the lesson to play, answer key included, and the learner's attempt once
they finish it.

The lesson player grades each answer as it's given; the server doesn't grade again. It checks
that a submitted attempt fits the lesson, and stores it. A lesson can be retried, except for
placement; each attempt is shuffled afresh.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel

from pupil_server.db import LOCAL_LEARNER, NotFound, new_id
from pupil_server.db.learning import AttemptRepo, LessonRepo, PlacementTaken
from pupil_server.learning.lesson import Answer, Attempt, GradedAttempt, Lesson, shuffled

router = APIRouter(prefix="/api/lessons", tags=["lessons"])

# One learner until remote mode adds accounts.
LEARNER = LOCAL_LEARNER


class AttemptSummary(BaseModel):
    attempt_id: str
    number: int
    correct: int
    total: int
    submitted_at: AwareDatetime


class LessonOut(BaseModel):
    lesson: Lesson
    """With its answers, for the player to grade; shuffled afresh on every request."""
    attempts: list[AttemptSummary]
    """The learner's attempts so far, first attempt first."""


class AttemptIn(BaseModel):
    answers: dict[str, Answer]
    """Question id to the learner's answer, as the player graded it, for every question."""


def _summary(graded: GradedAttempt) -> AttemptSummary:
    return AttemptSummary(
        attempt_id=graded.attempt.id,
        number=graded.number,
        correct=graded.correct,
        total=len(graded.results),
        submitted_at=graded.attempt.submitted_at,
    )


@router.get("/{lesson_id}")
async def get_lesson(lesson_id: str, request: Request) -> LessonOut:
    db = request.app.state.db
    try:
        lesson = await LessonRepo(db).get(LEARNER, lesson_id)
    except NotFound:
        raise HTTPException(404, "no such lesson") from None
    attempts = await AttemptRepo(db).for_lesson(LEARNER, lesson_id)
    return LessonOut(
        lesson=shuffled(lesson, random.Random()), attempts=[_summary(a) for a in attempts]
    )


@router.post("/{lesson_id}/attempts", status_code=201)
async def submit_attempt(lesson_id: str, body: AttemptIn, request: Request) -> AttemptSummary:
    attempt = Attempt(
        id=new_id("att"),
        lesson_id=lesson_id,
        answers=body.answers,
        submitted_at=datetime.now(UTC),
    )
    try:
        graded = await AttemptRepo(request.app.state.db).submit(LEARNER, attempt)
    except NotFound:
        raise HTTPException(404, "no such lesson") from None
    except PlacementTaken:
        raise HTTPException(409, "placement has already been taken") from None
    except (ValueError, TypeError) as exc:
        # Answers that don't fit the lesson: missing, extra, or of the wrong kind.
        raise HTTPException(422, str(exc)) from None
    # A topic's next lesson is prepared while the learner looks at their results.
    topic_id = await LessonRepo(request.app.state.db).topic_of(LEARNER, lesson_id)
    await request.app.state.runs.prepare(LEARNER, topic_id)
    return _summary(graded)
