"""Taking a lesson: the learner's view of it, without answers, checking each answer as it's
given, and submitting the whole attempt at the end.

Answers go straight from the lesson player to the grader, never through the agent. A lesson
can be retried, except for placement; each attempt is shuffled afresh.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel

from pupil_server.db import LOCAL_LEARNER, NotFound, new_id
from pupil_server.db.learning import AttemptRepo, LessonRepo, PlacementTaken
from pupil_server.learning.lesson import (
    Attempt,
    GradedAttempt,
    Lesson,
    LessonView,
    Response,
    learner_view,
)

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
    lesson: LessonView
    """Shuffled afresh on every request."""
    attempts: list[AttemptSummary]
    """The learner's attempts so far, first attempt first."""


class CheckIn(BaseModel):
    question_id: str
    response: Response


class CheckOut(BaseModel):
    correct: bool
    answer: str
    """The correct answer, as the learner should see it."""
    explanation: str


class AnswersIn(BaseModel):
    responses: dict[str, Response]
    """Question id to answer; skipped questions are left out and count as wrong."""


class ResultOut(BaseModel):
    question_id: str
    correct: bool
    response: Response | None
    """What the learner answered; None if they skipped it."""
    answer: str
    explanation: str


class AttemptOut(BaseModel):
    attempt_id: str
    number: int
    correct: int
    total: int
    results: list[ResultOut]


def _summary(graded: GradedAttempt) -> AttemptSummary:
    return AttemptSummary(
        attempt_id=graded.attempt.id,
        number=graded.number,
        correct=graded.correct,
        total=len(graded.results),
        submitted_at=graded.attempt.submitted_at,
    )


def _attempt_out(lesson: Lesson, graded: GradedAttempt) -> AttemptOut:
    results = []
    for r in graded.results:
        question = lesson.question(r.question_id)
        results.append(
            ResultOut(
                question_id=r.question_id,
                correct=r.correct,
                response=graded.attempt.responses.get(r.question_id),
                answer=question.answer_text(),
                explanation=question.explanation,
            )
        )
    return AttemptOut(
        attempt_id=graded.attempt.id,
        number=graded.number,
        correct=graded.correct,
        total=len(graded.results),
        results=results,
    )


async def _lesson(request: Request, lesson_id: str) -> Lesson:
    try:
        return await LessonRepo(request.app.state.db).get(LEARNER, lesson_id)
    except NotFound:
        raise HTTPException(404, "no such lesson") from None


@router.get("/{lesson_id}")
async def get_lesson(lesson_id: str, request: Request) -> LessonOut:
    lesson = await _lesson(request, lesson_id)
    attempts = await AttemptRepo(request.app.state.db).for_lesson(LEARNER, lesson_id)
    return LessonOut(
        lesson=learner_view(lesson, random.Random()),
        attempts=[_summary(a) for a in attempts],
    )


@router.post("/{lesson_id}/check")
async def check_answer(lesson_id: str, body: CheckIn, request: Request) -> CheckOut:
    """Grade one answer as it's given. Nothing is stored; the attempt is submitted at the end."""
    lesson = await _lesson(request, lesson_id)
    try:
        question = lesson.question(body.question_id)
        correct = question.grade(body.response)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from None
    return CheckOut(
        correct=correct, answer=question.answer_text(), explanation=question.explanation
    )


@router.post("/{lesson_id}/attempts", status_code=201)
async def submit_attempt(lesson_id: str, body: AnswersIn, request: Request) -> AttemptOut:
    lesson = await _lesson(request, lesson_id)
    attempt = Attempt(
        id=new_id("att"),
        lesson_id=lesson_id,
        responses=body.responses,
        submitted_at=datetime.now(UTC),
    )
    try:
        graded = await AttemptRepo(request.app.state.db).submit(LEARNER, attempt)
    except PlacementTaken:
        raise HTTPException(409, "placement has already been taken") from None
    except (ValueError, TypeError) as exc:
        # Answers to questions the lesson doesn't have, or of the wrong kind.
        raise HTTPException(422, str(exc)) from None
    return _attempt_out(lesson, graded)
